"""Routeur AUTO unique : A2 simulé ou exécuteur financé explicitement.

Luna classe, Sol rédige. Une décision Luna ne vaut jamais autorisation Sol.
"""
from copy import deepcopy
from .commercial_supervisor import require
from .semantic_cache import SemanticCache
from .storage import digest

FAILURE_MESSAGES={
 'TIMEOUT':'Délai de classification dépassé.',
 'NETWORK':'Connexion au fournisseur interrompue.',
 'HTTP':'Le fournisseur a retourné une erreur HTTP.',
 'EMPTY':'Réponse de classification vide.',
 'JSON_INVALID':'Réponse de classification illisible.',
 'SCHEMA_INVALID':'Réponse de classification non conforme.',
 'INCOMPLETE':'Réponse de classification incomplète.',
 'OUTPUT_LIMIT':'Plafond de sortie Luna atteint.',
 'REFUSAL':'Luna a explicitement refusé la classification.',
 'LOCAL':'Contrôle ou exécution locale en échec.',
 'UNKNOWN':'Cause technique non disponible.',
}

def failure_diagnostic(error,phase,emission,incomplete):
    from urllib.error import HTTPError,URLError
    code='LOCAL' if phase in ('PREPARE','TRANSPORT') else 'SCHEMA_INVALID'
    status=None
    if isinstance(error,HTTPError):
        code='HTTP';emission='CONFIRMED'
        status=error.code if type(error.code) is int and 100<=error.code<=599 else None
    elif isinstance(error,TimeoutError) or isinstance(error,URLError) and isinstance(error.reason,TimeoutError):code='TIMEOUT'
    elif isinstance(error,(URLError,ConnectionError)):code='NETWORK'
    elif str(error) in ('API_REQUEST_INVALID','API_OPERATION_IN_PROGRESS','API_DISABLED_OR_KEY_ABSENT','CREDENTIAL_INVALID'):
        code='LOCAL';emission='NOT_SENT'
    elif str(error)=='LUNA_REFUSAL':code='REFUSAL'
    elif str(error)=='LUNA_EMPTY':code='EMPTY'
    elif str(error)=='LUNA_INCOMPLETE':code='OUTPUT_LIMIT' if incomplete=='max_output_tokens' else 'INCOMPLETE'
    elif phase=='JSON':code='JSON_INVALID'
    return {'code':code,'phase':phase,'emission':emission,'http_status':status,'incomplete_reason':incomplete}

WORKFLOW_ENABLED=False

class LunaRouting:
    def __init__(self,store,*,simulated=False,qualification=False):
        self.store=store
        require(type(simulated) is bool,'LUNA_MODE_INVALID')
        self.semantic=SemanticCache(store,enabled=simulated,require_auto_decision=True,qualification=qualification)
        self.live=None
        self.direct=None
    def configure_live(self,campaign,transport,allocation):
        from .web_campaign import WebCampaign,daily,money
        from .sol_web_gateway import CampaignResponsesTransport,SimulatedWebTransport
        from .live_supervisor import TEST_ROOT
        require(type(campaign) is WebCampaign and daily(campaign.snapshot()['authorization']) and money(allocation) and allocation>0,'LUNA_CAMPAIGN_REQUIRED')
        require(type(transport) is (SimulatedWebTransport if campaign.test else CampaignResponsesTransport),'LUNA_TRANSPORT_REQUIRED')
        require(not campaign.test or self.store.root.is_relative_to(TEST_ROOT.resolve()),'LUNA_SIMULATION_TEST_ONLY')
        self.live=(campaign,transport,allocation)
    def _live_route(self,data,allow_emit):
        """Un seul essai durable. Les comparaisons A2 ne sont pas élargies.

        La décision de module peut être réutilisée ; les propositions sémantiques
        conservées ne deviennent jamais, par cette voie, un HIT CR clinique.
        """
        import hashlib,json,time
        from .storage import canonical
        from .semantic_contract import validate_decision,validate_request,MODEL
        from .functional_store import privacy_check
        campaign,transport,allocation=(None,self.direct,None) if self.direct else self.live
        test=self.semantic.cache.test if self.direct else campaign.test
        retry=data.get('luna_retry')
        clean={k:v for k,v in data.items() if k not in ('model','record_history','rewrite','luna_retry')}
        forced,query=self.semantic._mode(clean)
        if forced is not None:return None
        clean['query']=query
        def unavailable(message):return {'schema':'gary_v5_prepared_v1','status':'clarification','module':'AUTO','question':clean['query'],'message':message,'transport_enabled':False}
        def failed(message=None,op=None,identity=None):
            default={'code':'UNKNOWN','phase':'UNKNOWN','emission':'UNKNOWN','http_status':None,'incomplete_reason':None}
            if op is None:default.update(code='LOCAL',phase='PREPARE',emission='NOT_SENT')
            diagnostic=(op or {}).get('diagnostic',default)
            result={**unavailable(message or FAILURE_MESSAGES[diagnostic['code']]),'status':'routing_error','routing_diagnostic':diagnostic}
            if self.direct and retryable(op) and identity:
                result['luna_retry']={'previous':identity,'emission':diagnostic['emission']}
            return result
        def retryable(op):
            if not op:return False
            if op['state'] in ('REJECTED','UNCERTAIN'):return True
            if op['state']!='RUNNING':return False
            from .windows_app import process_owner_state
            return process_owner_state(op.get('owner'))=='GONE'
        financial=campaign.snapshot() if campaign else None
        if campaign and (financial['state']!='OPEN' or time.time()>=financial['authorization']['expires_at']):return unavailable('Campagne Luna fermée ou expirée. Aucune émission.')
        if campaign and not test and not transport.ready():return unavailable('Luna est indisponible. Aucun routage de secours.')
        _,_,requests,clarifications=self.semantic._requests(clean)
        hashes={m:digest(r) for m,r in requests.items()}
        scope={'data':clean,'targets':hashes,'protocol':self.semantic._protocol(),'campaign':financial['authorization']['campaign_id'] if campaign else 'DIRECT_V1'}
        base='luna_live_'+digest(scope);head_key=base+'_head';cache=self.semantic.cache
        def head(db):
            row=db.execute('SELECT value FROM metadata WHERE key=?',(head_key,)).fetchone()
            return row[0] if row else base
        with self.store.tx() as db:
            identity=head(db)
            row=db.execute('SELECT 1 FROM entries WHERE id=?',(identity,)).fetchone()
            op=cache._row(db,identity,'LUNA_ROUTE_LIVE_V1')[0] if row else None
        if retry is not None:
            if not (self.direct and allow_emit and retry==identity and retryable(op)):
                return failed('Nouvelle tentative refusée : la demande ou son état a changé.')
        if op is None or retry is not None:
            if not allow_emit:return failed('Décision Luna absente ou contexte modifié. Préparez à nouveau la demande.')
            if self.direct and not transport.ready():return failed('API désactivée ou clé absente.',op,identity)
            if campaign and (any(o['state'] in ('ENGAGED','EMITTING','UNCERTAIN') for o in financial['operations'].values()) or len(financial['operations'])>=financial['authorization']['max_requests'] or financial['available_eur_micros']<allocation):
                return failed('Campagne indisponible pour Luna.')
            previous=identity if retry is not None else None
            identity='luna_live_'+digest({'previous':previous}) if previous else base
            finance_id=identity.removeprefix('luna_live_')[:32]
            op={'state':'RUNNING','created_at':time.time(),'test':test,'previous_attempt':previous}
            if self.direct:
                import os
                from .windows_app import process_stamp
                pid=os.getpid()
                op['owner']={'pid':pid,'stamp':process_stamp(pid)}
            with self.store.tx() as db:
                if head(db)!=(previous or base) or db.execute('SELECT 1 FROM entries WHERE id=?',(identity,)).fetchone():
                    return failed('Classification Luna déjà engagée. Aucune seconde émission.')
                cache._put(db,'LUNA_ROUTE_LIVE_V1',op,identity)
                if previous:db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(head_key,identity))
            phase='PREPARE';emission='NOT_SENT';incomplete=None
            try:
                snapshot=self.semantic._snapshot(clean,routing_proposal=True)
                require(snapshot['state']=='PROPOSAL' and validate_request(snapshot['request']),'LUNA_PROPOSAL_INVALID')
                request=snapshot['request']
                if campaign:
                    if not test:transport.release.check(request,campaign)
                    campaign.reserve(finance_id,request,allocation=allocation,dependencies=scope['protocol'])
                    campaign.engage(finance_id,request,scope['protocol'])
                phase='TRANSPORT';emission='UNKNOWN'
                raw=transport.exchange(request,campaign,finance_id)
                phase='RESPONSE';emission='CONFIRMED'
                require(raw,'LUNA_EMPTY')
                require(type(raw) is bytes and len(raw)<=32000,'LUNA_RESPONSE_SIZE')
                def pairs(items):
                    result={}
                    for k,v in items:require(k not in result,'LUNA_DUPLICATE_JSON_FIELD');result[k]=v
                    return result
                phase='JSON'
                provider=json.loads(raw.decode('utf8'),object_pairs_hook=pairs)
                phase='VALIDATE';privacy_check(provider)
                response_sha=hashlib.sha256(raw).hexdigest()
                if campaign:
                    campaign.finish(finance_id,received=True,response_sha=response_sha)
                    campaign.record_usage(finance_id,provider.get('usage'))
                if provider.get('status')=='incomplete':
                    details=provider.get('incomplete_details')
                    reason=details.get('reason') if isinstance(details,dict) else None
                    incomplete=reason if reason in ('max_output_tokens','content_filter') else None
                    raise ValueError('LUNA_INCOMPLETE')
                require(provider.get('model')==MODEL and provider.get('status')=='completed','LUNA_RESPONSE_INCOMPLETE_OR_MODEL')
                texts=[]
                for item in provider.get('output',[]):
                    require(item.get('type') in ('message','reasoning'),'LUNA_OUTPUT_TYPE')
                    if item.get('type')=='message':
                        for content in item.get('content',[]):
                            require(content.get('type')=='output_text','LUNA_REFUSAL');texts.append(content['text'])
                require(''.join(texts).strip(),'LUNA_EMPTY')
                phase='JSON'
                decision=json.loads(''.join(texts),object_pairs_hook=pairs)
                phase='VALIDATE'
                decision_sha=validate_decision(decision,json.loads(request['input']))
                # Aucun résultat acquis sous un contexte désormais différent.
                require({m:digest(r) for m,r in self.semantic._requests(clean)[2].items()}==hashes,'LUNA_CONTEXT_CHANGED')
                op.update(state='DECIDED',scope=scope,request=request,finance_id=finance_id,decision=decision,decision_sha256=decision_sha,response_sha256=response_sha,provider_raw=raw.decode('utf8'))
            except BaseException as error:
                state=campaign.snapshot()['operations'].get(finance_id) if campaign else None
                if state and state['state'] in ('ENGAGED','EMITTING'):campaign.finish(finance_id)
                diagnostic=failure_diagnostic(error,phase,emission,incomplete)
                op.update(state='UNCERTAIN' if diagnostic['emission']=='UNKNOWN' else 'REJECTED',reason='LUNA_FAILED_NO_RETRY',diagnostic=diagnostic)
                with self.store.tx() as db:cache._put(db,'LUNA_ROUTE_LIVE_V1',op,identity)
                if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
                return failed(op=op,identity=identity)
            with self.store.tx() as db:cache._put(db,'LUNA_ROUTE_LIVE_V1',op,identity)
        if op['state']!='DECIDED':
            message=None
            if op['state']=='RUNNING':
                message=('Le processus de la tentative précédente a disparu. Une émission a pu avoir lieu.'
                         if retryable(op) else 'Classification Luna en cours ou propriétaire non vérifiable.')
            return failed(message,op,identity)
        require(op['scope']==scope and op['test'] is test,'LUNA_CONTEXT_CHANGED')
        packet=json.loads(op['request']['input']);require(validate_decision(op['decision'],packet)==op['decision_sha256'],'LUNA_DECISION_CORRUPT')
        if campaign:
            f=campaign.snapshot()['operations'][op['finance_id']]
            require(f['state'] in ('RECEIVED_PENDING_COST','OBSERVED','RECONCILED') and f['emissions']==1 and f['request_sha256']==digest(op['request']) and f['response_sha256']==op['response_sha256'],'LUNA_FINANCE_BINDING')
        require(hashlib.sha256(op['provider_raw'].encode('utf8')).hexdigest()==op['response_sha256'],'LUNA_RESPONSE_BINDING')
        original=json.loads(op['provider_raw']);text=''.join(c['text'] for item in original['output'] if item['type']=='message' for c in item['content'] if c['type']=='output_text')
        require(json.loads(text)==op['decision'],'LUNA_DECISION_RESPONSE_BINDING')
        module=op['decision']['module']
        if module=='CLARIFICATION':return unavailable('Luna demande une clarification. Aucun module inventé et aucune génération Sol.')
        if module not in requests:return failed('Le module sélectionné ne peut pas être préparé avec les paramètres actuels.')
        return {'schema':'gary_luna_route_c_v1','status':'routed','module':module,'routing_id':identity,'request_sha256':hashes[module],'prepared_request':deepcopy(requests[module]),'decision_sha256':op['decision_sha256'],'semantic_comparisons_reused':False,'medical_generation_authorized':False}
    def generation_route(self,data,*,allow_emit=False):
        """Reconnaissance du module, sans réutilisation des comparaisons périmées.

        La décision, son financement et le corps courant sont contrôlés. Un
        changement de candidats CD/CR seul ne nécessite pas de reclassifier
        la question ; leur admissibilité sera vérifiée par le cache courant.
        """
        if self.live is not None or self.direct is not None:return self._live_route(data,allow_emit)
        import json
        from .semantic_contract import validate_decision
        from .commercial_supervisor import OfflineSupervisor
        clean={k:v for k,v in data.items() if k not in ('model','record_history','rewrite')}
        if self.semantic.qualification:return self.prepare(clean)
        forced,_=self.semantic._mode(clean)
        if forced is not None:return None
        if self.semantic.enabled:
            for row in self.store.rows('A2_OPERATION_V1'):
                op=row['data']
                if digest(op.get('data'))!=digest(clean) or op.get('state')!='DECIDED':continue
                try:
                    op=self.semantic._operation(row['id']);packet=json.loads(op['request']['input'])
                    require(op['created_at']<=self.semantic.clock()<op['expires_at'] and packet['protocol_sha256']==self.semantic._protocol(),'LUNA_ROUTE_EXPIRED')
                    require(validate_decision(op['decision'],packet)==op['decision_sha256'],'LUNA_ROUTE_CORRUPT')
                    finance=OfflineSupervisor(op['supervisor_path'],self.semantic.clock).snapshot();f=finance['operations'][row['id']]
                    require(finance['campaign']['status']=='AUTHORIZED' and f['state']=='RECONCILED' and f['request_sha256']==digest(op['request']) and f['result_sha256']==op['response_fingerprint'],'LUNA_ROUTE_FINANCE_INVALID')
                    module=op['decision']['module']
                    if module=='CLARIFICATION':return {'schema':'gary_v5_prepared_v1','status':'clarification','module':'AUTO','question':clean['query'],'message':'Luna demande une clarification. Aucun module ni génération choisi automatiquement.','transport_enabled':False}
                    _,_,requests,clarifications=self.semantic._requests(clean)
                    if module not in requests:return clarifications.get(module,{'schema':'gary_v5_prepared_v1','status':'clarification','module':module,'question':clean['query'],'message':'Contexte à préciser pour le module retenu.','transport_enabled':False})
                    request=requests[module]
                    require(digest(request)==packet['target_request_sha256'][module],'LUNA_ROUTE_CONTEXT_CHANGED')
                    return {'schema':'gary_luna_route_c_v1','status':'routed','module':module,'routing_id':row['id'],'request_sha256':digest(request),'prepared_request':request,'decision_sha256':op['decision_sha256'],'semantic_comparisons_reused':False,'transport_enabled':False,'medical_generation_authorized':False}
                except (ValueError,KeyError,TypeError,OSError):
                    return {'schema':'gary_v5_prepared_v1','status':'clarification','module':'AUTO','question':clean['query'],'message':'La décision Luna conservée n’est plus admissible. Aucun appel ni routage de secours.','transport_enabled':False}
        result=self.prepare(clean)
        if result and result.get('routing',{}).get('state') in ('RUNNING','UNCERTAIN','REJECTED'):
            return {'schema':'gary_v5_prepared_v1','status':'clarification','module':'AUTO','question':clean['query'],'message':'Classification Luna interrompue ou refusée ; aucune relance automatique.','transport_enabled':False}
        return result
    def prepare(self,data):
        data={k:v for k,v in data.items() if k not in ('model','record_history','rewrite')}
        forced,_=self.semantic._mode(data)
        if forced is not None and not self.semantic.enabled:return None
        proposal=self.semantic.prepare(data)
        if proposal.get('state')=='DISABLED':
            return {'schema':'gary_v5_prepared_v1','status':'clarification','module':'AUTO','question':data['query'],
                    'message':'Luna est indisponible : le routage AUTO reste désactivé. Sélectionnez un module. Aucun appel ni routage lexical de secours.',
                    'request_sha256':None,'transport_enabled':False,'medical_generation_authorized':False}
        if forced is not None and proposal.get('state') in ('EXACT_CR','EXACT_CD','MISS','CLARIFICATION'):return None
        if proposal.get('state')=='DECIDED':return self.confirm(proposal['operation_id'],data)
        return {'schema':'gary_luna_route_c_v1','status':'routing_required','routing':proposal,
                'transport_enabled':False,'medical_generation_authorized':False}
    def classify_simulated(self,identity,**kwargs):
        return self.semantic.compare_simulated(identity,**kwargs)
    def confirm(self,identity,data):
        data={k:v for k,v in data.items() if k not in ('model','record_history','rewrite')}
        # Revalide contexte, preuves, TTL, préférences et finances sans émission.
        result=self.semantic.confirm(identity,data)
        if result['state']=='CLARIFICATION':return {'schema':'gary_luna_route_c_v1','status':'clarification','routing':result,'transport_enabled':False}
        module=result['module'];snapshot=self.semantic._fresh(self.semantic._operation(identity),data)
        request=deepcopy(snapshot['requests'][module])
        require(request['model']=='gpt-6.1-sol','SOL_GENERATION_MODEL_REQUIRED')
        return {'schema':'gary_luna_route_c_v1','status':'routed','module':module,'routing_id':identity,
                'request_sha256':digest(request),'prepared_request':request,'cache_plan':result,
                'documentary_plan':{'schema':'gary_cd_route_plan_c_v1','documents':result.get('documents',[]),
                                    'consumption':'EXPLICIT_FUTURE_ORCHESTRATOR_ONLY'},
                'transport_enabled':False,'medical_generation_authorized':False}

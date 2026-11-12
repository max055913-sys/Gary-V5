"""Frontière HTTP de génération : préparation serveur, nonce et refus par défaut.

Le test injecte ses objets uniquement au constructeur Python du serveur, jamais
par une route ou un champ de navigateur. Aucun producteur réel n'est activé.
"""
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import threading
import time
from decimal import Decimal
from .commercial_supervisor import require
from .storage import digest,canonical
from .live_supervisor import LiveSupervisor, LIVE_PATH, TEST_ROOT, prepare_live_request
from . import live_transport as transport_module
from .live_transport import LiveGeneration, SimulatedTransport
from .generation_metrics import metrics
from . import live_supervisor as supervisor_module


class GenerationGateway:
    def __init__(self, runtime, *, test_directory=None, scenario='complete',luna_routing=None,fixture_model_identity=False):
        self.runtime=runtime;self.entries={};self.lock=threading.Lock()
        self.test_directory=Path(test_directory) if test_directory is not None else None
        self.scenario=scenario
        require(type(fixture_model_identity) is bool and (not fixture_model_identity or self.test_directory is not None),'FIXTURE_MODEL_OFFLINE_ONLY')
        self.fixture_model_identity=fixture_model_identity
        self.luna_routing=luna_routing
        if luna_routing is not None:
            from .luna_routing import LunaRouting
            require(type(luna_routing) is LunaRouting and self.test_directory is not None and luna_routing.store.root==runtime.store.root,'LUNA_TEST_INJECTION_ONLY')
        from .functional_store import FunctionalStore
        self.functional=FunctionalStore(runtime.store) if getattr(runtime,'store',None) is not None else None
        from .documentary_cache import DocumentaryCache
        self.cache=DocumentaryCache(runtime.store) if self.functional else None
        if self.test_directory is not None:
            require(self.test_directory.resolve().is_relative_to(TEST_ROOT.resolve()),'TEST_PATH_REQUIRED')

    def live_packet(self,request):
        """Paquet préqualifié sur disque serveur, jamais reçu par HTTP."""
        require(transport_module.NETWORK_RELEASE is not None and transport_module.NETWORK_RELEASE in transport_module.TRUSTED_RELEASES,'LIVE_NETWORK_SEALED')
        packet_path=LIVE_PATH.parent/'approved_packet.json'
        require(packet_path.is_file() and not packet_path.is_symlink(),'QUALIFIED_PACKET_ABSENT')
        packet=json.loads(packet_path.read_text('utf8'))
        require(type(packet) is dict and set(packet) in ({'approval','bound'},{'approval','bound','registry'}),'QUALIFIED_PACKET_INVALID')
        path=LIVE_PATH
        if 'registry' in packet:
            require(type(packet['registry']) is str and __import__('re').fullmatch(r'[0-9a-f]{32}\.sqlite',packet['registry']),'REGISTRY_PATH_REFUSED')
            path=LIVE_PATH.parent/'campaigns'/packet['registry']
        s=LiveSupervisor(path);state=s.snapshot()
        require(state['state']=='DRAFT' and state['request_sha256']==digest(request),'CAMPAIGN_UNAVAILABLE')
        for doc,kind,pins in [(packet['approval'],'HUMAN_LIVE_APPROVAL',supervisor_module.TRUSTED_APPROVALS),(packet['bound'],'ALL_IN_EUR_BOUND',supervisor_module.TRUSTED_BOUNDS)]:
            s.proof(doc,kind,pins)
            require(doc.get('campaign')==state['campaign'] and doc.get('request_sha256')==digest(request),'QUALIFIED_PACKET_SCOPE')
            require(type(doc.get('expires_ms')) is int and int(time.time()*1000)<doc['expires_ms'],'QUALIFIED_PACKET_EXPIRED')
        s.refresh_draft(request)
        return s,packet

    def prepare_request(self,data):
        core={k:v for k,v in data.items() if k in {'query','module','profile','privacy_confirmed','depth','context_policy','model'}}
        from .functional_store import privacy_check
        privacy_check(core)
        # Compatibilité avec le contrat interne historique : contrôle serveur,
        # pas déclaration humaine fabriquée par le navigateur.
        if 'privacy_confirmed' not in core:core['privacy_confirmed']=True
        prepared,request=self.runtime.prepare_request(core)
        if request is None:return prepared,None
        body=json.loads(request['input'])
        if data.get('include_personal_suivi') is True and body['module']=='SUIVI' and self.functional:
            value=self.functional.options()['personal_suivi']
            if value:body['personal_preferences']={'label':'Préférence personnelle','text':value,'authority':'USER_PREFERENCE_NOT_OFFICIAL_RECOMMENDATION'}
        if data.get('renal_context'):
            renal=data['renal_context'];require(type(renal) is dict,'RENAL_CONTEXT_INVALID')
            require(body['module']=='TTT','RENAL_CONTEXT_MODULE_INVALID')
            if 'kind' in renal:
                import re
                require(set(renal)=={'kind','value'} and renal['kind']=='REPORTED_EGFR','RENAL_CONTEXT_INVALID')
                value=renal['value'];require(type(value) is str and len(value)<=32,'RENAL_CONTEXT_INVALID')
                if value!='':
                    require(re.fullmatch(r'[0-9]+(?:[.,][0-9]+)?',value) is not None,'RENAL_CONTEXT_INVALID')
                    body['provided_renal_function']={'kind':'REPORTED_EGFR','values':{'value':value,'unit':'mL/min/1,73 m²'},'method':'USER_REPORTED_NOT_CALCULATED','converted_to_cockcroft_gault':False}
            else:
                # Contrat historique inchangé : ne jamais rebaptiser ces valeurs DFG.
                require(set(renal)<={'value','unit','method','source_date'} and all(type(v) is str and len(v)<=200 for v in renal.values()),'RENAL_CONTEXT_INVALID')
                body['provided_renal_function']={'values':renal,'method':'USER_REPORTED_NOT_CALCULATED'}
        if data.get('rewrite'):
            require(self.functional is not None and body['module']=='FICH','REWRITE_INVALID')
            rewrite=data['rewrite'];require(type(rewrite) is dict and set(rewrite)=={'draft_id','revision','instruction'},'REWRITE_INVALID')
            from .functional_store import text
            text(rewrite['instruction'],1000);require(rewrite['instruction'].strip(),'REWRITE_INVALID')
            draft=self.functional.draft(rewrite['draft_id']);require(draft['revision']==rewrite['revision'],'REVISION_CONFLICT')
            body['patient_draft']={'id':draft['id'],'revision':draft['revision'],'text':draft['versions'][-1]['text'],
                                   'sources':draft['sources'],'status':'UNVALIDATED_INPUT_FOR_REWRITE'}
            body['rewrite_instruction']={'text':rewrite['instruction'],'origin':'USER_REQUEST'}
        request['input']=canonical(body) if self.fixture_model_identity else json.dumps(body,ensure_ascii=False)
        privacy_check(body)
        return prepared,request

    def cache_plan(self,request,*,allow_cr=True,skip_reason='EXPLICIT_REFRESH'):
        if self.cache is None:return request,None
        plan=self.cache.resolve(request,allow_cr=allow_cr,skip_reason=skip_reason)
        return self.cache.enrich(request,plan),plan

    def local_result(self,request,display,state,data,*,test,evidence=None,origin=None):
        if not self.functional:return display
        try:
            if display.get('module')=='FICH' and display.get('text','').strip():
                draft=self.functional.create_draft(display['question'],display['text'],sources=display.get('references',[]),
                    source_key=origin,test=test)
                display['draft_id']=draft['id']
            display.update(self.functional.record(request,display,state,history_id=data.get('history_id'),test=test,evidence=evidence))
        except Exception:
            display['local_save_warning']='Sauvegarde locale incomplète ; originaux de preuve conservés, aucune nouvelle génération.'
        return display

    def prepare(self,data):
        require(type(data) is dict and set(data)<={'query','module','profile','privacy_confirmed','depth','context_policy','model','history_id','record_history','rewrite','include_personal_suivi','renal_context'},'PREPARATION_FIELDS_REFUSED')
        require('record_history' not in data or type(data['record_history']) is bool,'HISTORY_POLICY_INVALID')
        require('include_personal_suivi' not in data or type(data['include_personal_suivi']) is bool,'PERSONAL_PREFERENCE_INVALID')
        if self.luna_routing is not None:
            routed=self.luna_routing.prepare(data)
            if routed is not None:return routed
        else:
            from .routing import command_parts
            forced,_=command_parts(data.get('query'),data.get('module','AUTO'))
            if forced is None:
                from .luna_routing import LunaRouting
                return LunaRouting(self.runtime.store).prepare(data)
        start=time.perf_counter()
        prepared,request=self.prepare_request(data)
        if request is None:return prepared
        if data.get('history_id'):
            require(self.functional is not None,'HISTORY_UNAVAILABLE')
            previous=self.functional.history(data['history_id'])['versions'][-1]
            require(previous['question']==prepared['question'] and previous['module']==prepared['module'],'HISTORY_REFRESH_SCOPE_MISMATCH')
        blockers=[]
        candidate=prepare_live_request(request)
        cache_summary=None
        try:
            candidate,plan=self.cache_plan(candidate,allow_cr=not bool(data.get('history_id')))
            if plan:
                cache_summary={k:plan[k] for k in ('CR','CD')}
                if plan['CR']['decision']=='HIT':
                    display=plan['display'];display['cache']={'kind':'CR',**plan['CR'],'clinical_validation':False}
                    return self.local_result(candidate,display,'CACHE_REUSED',data,test=display['test'],evidence=plan.get('evidence_directory'),
                        origin={'cache_entry':plan['CR']['entry_id'],'consultation':secrets.token_hex(16)})
        except Exception:
            blockers.append('Cache local indisponible ou incohérent. Aucune émission déclenchée ; vérifier le stockage.')
        if self.test_directory is None:
            try:self.live_packet(candidate)
            except Exception:
                blockers+=['Borne totale de 1 € non qualifiée : contenu Web facturable, conversion, frais et taxes.',
                           'Aucune nouvelle autorisation LIVE reconnue ; transport scellé.']
        identifier=secrets.token_hex(16);challenge=secrets.token_urlsafe(32)
        entry={'id':identifier,'challenge':challenge,'created':time.monotonic(),'data':dict(data),'request':candidate,
                'sha':digest(candidate),'used':False,'state':'PREPARED','phases':['PREPARED'],'blockers':blockers,'test':self.test_directory is not None,'cache':cache_summary,
               'confirmation':prepared['module']+' — '+prepared['question']+' — 1,00 € — un appel',
               'metrics':metrics(timings={'preparation_ms':(time.perf_counter()-start)*1000},test=self.test_directory is not None)}
        with self.lock:
            self.entries={k:v for k,v in self.entries.items() if time.monotonic()-v['created']<300 or v['used']}
            require(len(self.entries)<64,'PREPARATION_CAPACITY_REACHED');self.entries[identifier]=entry
        return {**prepared,'request_sha256':entry['sha'],'cache_decisions':cache_summary,'generation':{'id':identifier,'challenge':challenge,
                'ready':not blockers,'blockers':blockers,'test':entry['test'],'ceiling_eur':'1.00','max_calls':1,
                'confirmation':entry['confirmation'],
                'service_tier':'default','estimated_eur':None,'estimated_usd':None,'metrics':entry['metrics']}}

    def status(self,identifier):
        with self.lock:
            e=self.entries.get(identifier);require(e is not None,'PREPARATION_ABSENT')
            return self.status_unlocked(e)

    def confirm(self,data):
        require(type(data) is dict and set(data)=={'id','challenge','confirmation'},'CONFIRMATION_INVALID')
        with self.lock:
            e=self.entries.get(data['id']);require(e is not None,'PREPARATION_ABSENT')
            require(type(data['challenge']) is str and hmac.compare_digest(e['challenge'],data['challenge']),'CONFIRMATION_INVALID')
            require(data['confirmation']==e['confirmation'],'EXPLICIT_CONFIRMATION_REQUIRED')
            require(not e['used'],'SECOND_EMISSION_REFUSED')
            require(0<=time.monotonic()-e['created']<=30,'PREPARATION_EXPIRED')
            if e['blockers']:
                e['state']='BLOCKED';e['phases'].append('BLOCKED');return self.status_unlocked(e)
            # Réassemblage avec les préférences effectives ; aucun corps client admis.
            _,request=self.prepare_request(e['data']);current=prepare_live_request(request)
            current,_=self.cache_plan(current,allow_cr=False,skip_reason='CONFIRMATION_RECHECK')
            require(digest(current)==e['sha'],'REQUEST_CHANGED')
            e['used']=True;e['state']='AUTHORIZING';e['phases'].append('AUTHORIZING')
        start=time.perf_counter()
        try:
            if e['test']:
                folder=self.test_directory/e['id'];folder.mkdir(parents=True,exist_ok=False)
                s=LiveSupervisor.create(current,folder/'TEST_ONLY.sqlite',test=True)
                state=s.snapshot();base={'test':True,'campaign':state['campaign'],'request_sha256':state['request_sha256'],'expires_ms':int(time.time()*1000)+30000}
                s.approve(dict(base,kind='HUMAN_LIVE_APPROVAL',max_calls=1,ceiling_eur_micros=1000000,human_identity='TEST_ONLY',decision_reference='UI_TEST'),
                          dict(base,kind='ALL_IN_EUR_BOUND',max_eur_micros=900000,all_costs_included=True))
            else:
                s,packet=self.live_packet(current);s.approve(packet['approval'],packet['bound'])
                folder=LIVE_PATH.parent/'evidence'/s.snapshot()['campaign']
                folder.mkdir(parents=True,exist_ok=False)
            e['supervisor']=s;flow=LiveGeneration(s)
            def checkpoint(stage):
                e['state']={'reserved':'RESERVED','engaged':'EMITTING','emitted':'RECEIVED'}[stage]
                e['phases'].append(e['state'])
            flow.checkpoint=checkpoint
            reply=flow.run(current,transport=SimulatedTransport(self.scenario,request_model_fixture=self.fixture_model_identity) if e['test'] else None,evidence_directory=folder/'evidence')
            e['directory']=Path(reply['evidence_directory'])
            response=json.loads((e['directory']/'reponse_fournisseur.json').read_text('utf8')) if (e['directory']/'reponse_fournisseur.json').exists() else {}
            durations={**e['metrics']['timings_ms'],**reply['timings'],'server_run_ms':(time.perf_counter()-start)*1000}
            e['metrics']=metrics(response,durations,test=e['test'])
            e['state']='DISPLAYED' if reply['result'] is not None else 'INCOMPLETE' if reply['provider_status']=='incomplete' else 'REFUSED_OR_INVALID'
            e['phases'].append(e['state'])
            e['reply']=reply
            display=self.display(e,response)
            if self.cache and reply['result'] is not None:
                try:
                    cached=self.cache.capture(current,display,e['directory'])
                    if cached.get('entry_id'):display['cache_entry_id']=cached['entry_id']
                except Exception:
                    display['cache_warning']='Réponse conservée, mais alimentation du cache refusée ou indisponible. Aucune relance automatique.'
                    try:self.cache.failure('CD/CR','PUBLICATION_FAILED_OR_REFUSED')
                    except Exception:pass
            display=self.local_result(current,display,e['state'],e['data'],test=e['test'],evidence=e['directory'],origin={'generation':e['id'],'parent':e['data'].get('rewrite')})
            return {**self.status_unlocked(e),'display':display,'evidence_available':True}
        except BaseException as exc:
            e['state']='UNCERTAIN';e['metrics']['completeness']='unknown'
            e['phases'].append('UNCERTAIN')
            e['metrics']['timings_ms']['server_run_ms']=(time.perf_counter()-start)*1000
            if self.functional:
                try:
                    should_record=True
                    if not should_record:return {**self.status_unlocked(e),'error':'Émission interrompue ou refusée ; coût inconnu, aucune relance autorisée.'}
                    body=json.loads(e['request']['input'])
                    error_display={'schema':'gary_v5_generation_display_v1','module':body['module'],'question':body['question'],
                                   'text':'','status':'technical_error','references':[],'test':e['test'],'clinical_validation':False}
                    self.functional.record(e['request'],error_display,'UNCERTAIN',history_id=e['data'].get('history_id'),test=e['test'])
                except Exception:pass # Ne masquer ni l'incertitude ni les preuves par un échec de stockage.
            return {**self.status_unlocked(e),'error':'Émission interrompue ou refusée ; coût inconnu, aucune relance autorisée.'}

    def status_unlocked(self,e):
        if 'supervisor' in e:
            state=e['supervisor'].snapshot()
            if state['state'] in {'RECONCILED','FROZEN'} and state.get('receipt'):
                e['supervisor'].proof(state['receipt'],'ACTUAL_EUR_COST',supervisor_module.TRUSTED_RECEIPTS)
                require(state['receipt'].get('amount_eur_micros')==state['actual_eur_micros'],'RECEIPT_DIVERGENT')
                e['metrics']['confirmed_eur']=str(Decimal(state['actual_eur_micros'])/1_000_000)
                if 'directory' in e:
                    from .live_evidence import attach_reconciliation
                    attach_reconciliation(e['directory'],e['supervisor'])
        return {**{k:e[k] for k in ('id','state','phases','blockers','test','metrics')},'evidence_available':'directory' in e}

    def display(self,e,response):
        if e['reply']['result'] is not None:return {**e['reply']['result'],'test':e['test']}
        text=(e['directory']/'reponse_gary_brute.txt').read_bytes().decode('utf8') if (e['directory']/'reponse_gary_brute.txt').exists() else ''
        original=json.loads(e['request']['input'])
        references=[];refusal=False
        if type(response) is dict and type(response.get('output')) is list:
            for item in response['output']:
                if type(item) is not dict:continue
                for part in item.get('content',[]):
                    if part.get('type')=='refusal':refusal=True
                    for a in part.get('annotations',[]):
                        if a.get('type')=='url_citation' and type(a.get('url')) is str and a['url'].startswith('https://'):
                            references.append({'url':a['url'],'title':a.get('title')})
        return {'schema':'gary_v5_generation_display_v1','module':original['module'],'question':original['question'],'text':text,
                'test':e['test'],'status':'partial' if response.get('status')=='incomplete' else 'refusal' if refusal else 'technical_error',
                'references':references,'clinical_validation':False}

    def artifact(self,identifier,name):
        allowed={'reponse_gary_brute.txt','reponse_fournisseur.json','manifest.json','Gary_PATH_Hypercalcemie_reponse_originale.pdf','Gary_reponse_originale.pdf','Gary_TEST_reponse_originale.pdf','capture_reference.png'}
        require(name in allowed,'ARTIFACT_REFUSED')
        e=self.entries.get(identifier);require(e is not None and 'directory' in e,'ARTIFACT_ABSENT')
        p=e['directory']/name;require(p.is_file() and not p.is_symlink(),'ARTIFACT_ABSENT')
        return p.read_bytes()

    def capture(self,data):
        require(type(data) is dict and set(data)=={'id','html','width','text','background'},'SNAPSHOT_INVALID')
        with self.lock:
            e=self.entries.get(data['id']);require(e is not None and 'directory' in e,'ARTIFACT_ABSENT')
            require(not e.get('export_started'),'VISUAL_EXPORT_ALREADY_STARTED')
            display=e['reply'].get('result')
            expected=display['text'] if display is not None else (e['directory']/'reponse_gary_brute.txt').read_bytes().decode('utf8')
            require(data['text']==expected,'SNAPSHOT_TEXT_MISMATCH')
            e['export_started']=True
        from .visual_export import capture
        try:
            capture(e['directory'],data['html'],data['width'],expected,background=data['background'],test=e['test'])
            return {'state':'VISUAL_REVIEW_REQUIRED','retry_generation':False}
        except Exception:
            return {'state':'VISUAL_EXPORT_FAILED','originals_preserved':True,'retry_generation':False}

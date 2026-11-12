"""A2 hors réseau : coordination hybride, décisions persistantes et refus fermé.

Aucune route HTTP, clé ou transport LIVE. Le chemin A est utilisé sans changement.
L'activation simulée exige TEST_ROOT et le superviseur OFFLINE_ONLY existant.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
import time
from .storage import canonical,digest
from .commercial_supervisor import require,OfflineSupervisor
from .documentary_cache import DocumentaryCache,bytes_sha,iso
from .functional_store import privacy_check
from .generation_gateway import GenerationGateway
from .application import Runtime
from .live_supervisor import prepare_live_request
from .module_rules import RULES,ROLES
from .semantic_candidates import LocalCandidates
from .semantic_contract import VERSION,MODULES,canonical_question,sensitive_facts,request_units,validate_decision,request_parameters

SEMANTIC_ENABLED=False
QUALIFIED_FOR_LIVE=False

def comparison_context(body):
    result={'profile':deepcopy(body.get('profile',{}))}
    if 'provided_renal_function' in body:result['provided_renal_function']=deepcopy(body['provided_renal_function'])
    result['private_dependencies_sha256']=digest({k:body[k] for k in ('personal_preferences','patient_draft','rewrite_instruction') if k in body})
    return result

class SimulatedLunaDecision:
    """Seulement une réponse de fixture ; aucun mécanisme d'émission réseau."""
    def __init__(self,value):self.value=value;self.calls=0
    def respond(self,request):
        self.calls+=1
        if isinstance(self.value,BaseException):raise self.value
        return canonical(self.value).encode('utf8') if type(self.value) is dict else self.value

class SemanticCache:
    def __init__(self,store,*,enabled=SEMANTIC_ENABLED,clock=time.time,require_auto_decision=False,qualification=False):
        self.store=store;self.cache=DocumentaryCache(store,clock);self.local=LocalCandidates(self.cache);self.clock=clock
        require(type(enabled) is bool,'A2_ENABLE_INVALID')
        require(not enabled or self.cache.test,'A2_UNQUALIFIED_PRODUCTION_DISABLED')
        require(type(qualification) is bool and (not qualification or self.cache.test and enabled),'A2_QUALIFICATION_TEST_ONLY')
        self.enabled=enabled;self.qualification=qualification;self.require_auto_decision=require_auto_decision;self.gateway=GenerationGateway(Runtime(store))
    def _event(self,db,event,identity):
        db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('A2_'+event,canonical({'operation_id':identity,'test':self.cache.test}),self.clock()))
    def _protocol(self):
        root=Path(__file__).parent
        return digest({'files':{name:bytes_sha(root/name) for name in ('semantic_contract.py','semantic_candidates.py','semantic_cache.py')},'profile':'LUNA_EQUIVALENCE_NATIVE_F3_V1' if self.qualification else 'A2_STRICT_V1'})
    def _mode(self,data):
        require(type(data) is dict and set(data)<={'module','query','profile','depth','context_policy','privacy_confirmed','include_personal_suivi','renal_context','history_id'},'A2_INPUT_FIELDS')
        privacy_check(data);query=data.get('query');mode=data.get('module','AUTO')
        require(type(query) is str and bool(query.strip()) and len(query)<=1000 and mode in ('AUTO',*MODULES),'A2_INPUT_INVALID')
        from .routing import command_parts
        forced,without=command_parts(query,mode)
        return forced,without if forced is None or self.qualification else query
    def _requests(self,data):
        forced,query=self._mode(data);requests={};clarifications={}
        for module in ((forced,) if forced else MODULES):
            values={k:v for k,v in data.items() if k not in ('history_id',)};values.update(module=module,query=query)
            prepared,request=self.gateway.prepare_request(values)
            if request is not None:
                # Une persistance JSON peut réordonner les clés sans changer les valeurs.
                request['input']=canonical(json.loads(request['input']))
                if self.qualification:
                    from .sol_web_profile import apply
                    requests[module]=apply(request)
                else:requests[module]=prepare_live_request(request)
            else:clarifications[module]=prepared
        return forced,query,requests,clarifications
    def _snapshot(self,data,*,routing_proposal=False):
        forced,query,requests,clarifications=self._requests(data);exact={};hits=[]
        for module,request in requests.items():
            plan=self.cache.resolve(request,allow_cr=not bool(data.get('history_id')));exact[module]=plan
            if plan['CR']['decision']=='HIT':hits.append((module,plan))
        if len(hits)==1 and forced is not None:
            return {'state':'EXACT_CR','module':hits[0][0],'plan':hits[0][1]}
        if forced and forced in clarifications:return {'state':'CLARIFICATION','module':forced,'reason':'CONTEXT_REQUIRED'}
        if not self.enabled and not routing_proposal:return {'state':'DISABLED','exact_plans':exact,'live_enabled':False}
        for request in requests.values():self.local.register_context(request)
        candidates=self.local.collect(requests,include_zero=self.qualification)
        # Une réserve de A ne devient pas un HIT grâce à A2.
        candidates=[v for v in candidates if v['kind']!='CR' or (not data.get('history_id') and exact[v['module']]['CR']['decision']!='REJECT')]
        if forced and not any(v['kind']=='CR' for v in candidates) and exact[forced]['CD']['decision']=='HIT':
            return {'state':'EXACT_CD','module':forced,'plan':exact[forced]}
        if forced and not candidates:return {'state':'MISS','module':forced,'reason':'NO_ADMISSIBLE_CANDIDATES'}
        exported=[]
        for v in candidates:
            c={k:deepcopy(v[k]) for k in ('id','kind','module','row_sha256','text')}
            c['question']=v['context']['question'];c['profile']=v['context'].get('profile',{})
            c['clinical_context']=comparison_context(v['context'])
            if v['kind']=='CD':c['document_metadata']={k:val for k,val in v['document'].items() if k!='excerpt'}
            exported.append(c)
        packet={'schema':VERSION,'protocol_sha256':self._protocol(),'fixed_module':forced,'route_required':forced is None,
                'question':query,'profile':deepcopy(data.get('profile',{})),'request_units':request_units(query),
                'roles':{m:ROLES[m] for m in (MODULES if forced is None else (forced,))},'candidates':exported,
                'input_sha256':digest(data),'target_request_sha256':{m:digest(r) for m,r in requests.items()}}
        packet['clinical_context_by_module']={m:comparison_context(json.loads(r['input'])) for m,r in requests.items()}
        privacy_check(packet);require(len(canonical(packet))<=48000,'A2_PACKET_LIMIT_NO_TRUNCATION')
        request={**request_parameters(),'input':canonical(packet)}
        return {'state':'PROPOSAL','request':request,'packet':packet,'candidates':candidates,'requests':requests,'clarifications':clarifications}
    def prepare(self,data):
        snapshot=self._snapshot(data)
        if snapshot['state']!='PROPOSAL':return snapshot
        identity='a2_'+digest(snapshot['request'])[:48]
        with self.store.tx() as db:
            if db.execute('SELECT 1 FROM entries WHERE id=?',(identity,)).fetchone():
                old=self.cache._row(db,identity,'A2_OPERATION_V1')[0];require(old['request']==snapshot['request'] and old['data']==data,'A2_OPERATION_COLLISION')
                return {'state':old['state'],'operation_id':identity,'request':deepcopy(old['request']),'created_ms':old['created_ms'],'live_enabled':False}
            now=self.clock();value={'schema':VERSION,'test':True,'created_at':now,'created_ms':int(now*1000),'expires_at':now+300,
                   'data':deepcopy(data),'request':snapshot['request'],'state':'PENDING','decision':None,'decision_sha256':None,'supervisor_path':None}
            self.cache._put(db,'A2_OPERATION_V1',value,identity);self._event(db,'PREPARED',identity)
        return {'state':'PENDING','operation_id':identity,'request':deepcopy(value['request']),'created_ms':value['created_ms'],'live_enabled':False}
    def _operation(self,identity):
        with self.store.tx() as db:value=self.cache._row(db,identity,'A2_OPERATION_V1')[0]
        require(value['schema']==VERSION and value['test'] is True and self.cache.test,'A2_NAMESPACE_REFUSED');return value
    def _fresh(self,operation,data):
        require(self.enabled and self.cache.test,'A2_DISABLED')
        require(digest(data)==digest(operation['data']),'A2_CONTEXT_CHANGED')
        require(operation['created_at']<=self.clock()<operation['expires_at'],'A2_DECISION_EXPIRED')
        snapshot=self._snapshot(data)
        require(snapshot['state']=='PROPOSAL' and digest(snapshot['request'])==digest(operation['request']),'A2_INPUT_OR_CANDIDATES_CHANGED')
        return snapshot
    def compare_simulated(self,identity,*,supervisor,bound,transport,receipt=None):
        require(self.enabled and self.cache.test and type(supervisor) is OfflineSupervisor and type(transport) is SimulatedLunaDecision,'A2_OFFLINE_ONLY')
        value=self._operation(identity);self._fresh(value,value['data'])
        if value['state']=='DECIDED':
            require(value['supervisor_path']==str(supervisor.path),'A2_SUPERVISOR_CHANGED');return {'state':'DECIDED','calls':0,'live_enabled':False}
        with self.store.tx() as db:
            value=self.cache._row(db,identity,'A2_OPERATION_V1')[0];require(value['state']=='PENDING','A2_ALREADY_ATTEMPTED')
            value.update(state='RUNNING',supervisor_path=str(supervisor.path));self.cache._put(db,'A2_OPERATION_V1',value,identity);self._event(db,'ATTEMPT_COMMITTED',identity)
        engaged=False;received=False
        try:
            op=supervisor.reserve(identity,value['request'],value['created_ms'],bound);require(op['id']==identity,'A2_FINANCIAL_OPERATION_CONFLICT')
            self._fresh(value,value['data']);supervisor.engage_fixture(identity,value['request']);engaged=True
            raw=transport.respond(value['request']);received=True
            require(type(raw) is bytes and len(raw)<=32000,'A2_RESPONSE_SIZE')
            supervisor.outcome(identity,'RECEIVED',digest(raw.decode('utf8')))
            def pairs(items):
                result={}
                for key,item in items:require(key not in result,'A2_DUPLICATE_JSON_FIELD');result[key]=item
                return result
            decision=json.loads(raw.decode('utf8'),object_pairs_hook=pairs)
            packet=json.loads(value['request']['input']);decision_sha=validate_decision(decision,packet)
            self._fresh(value,value['data'])
            if receipt is not None:supervisor.reconcile_fixture(identity,receipt)
            with self.store.tx() as db:
                current=self.cache._row(db,identity,'A2_OPERATION_V1')[0];require(current['state']=='RUNNING','A2_OPERATION_CHANGED')
                current.update(state='DECIDED',decision=decision,decision_sha256=decision_sha,response_fingerprint=digest(raw.decode('utf8')));self.cache._put(db,'A2_OPERATION_V1',current,identity);self._event(db,'DECISION_STORED',identity)
            return {'state':'DECIDED','calls':1,'live_enabled':False}
        except BaseException as error:
            if engaged:
                try:
                    state=supervisor.snapshot()['operations'][identity]
                    if state['state']=='ENGAGED':supervisor.outcome(identity,'TIMEOUT' if isinstance(error,TimeoutError) else 'INCOMPLETE')
                    if receipt is not None and received:supervisor.reconcile_fixture(identity,receipt)
                except Exception:pass
            else:
                try:supervisor.cancel_unengaged(identity)
                except Exception:pass
            with self.store.tx() as db:
                current=self.cache._row(db,identity,'A2_OPERATION_V1')[0];current['state']='UNCERTAIN' if engaged and not received else 'REJECTED'
                self.cache._put(db,'A2_OPERATION_V1',current,identity);self._event(db,current['state'],identity)
            return {'state':current['state'],'reason':'A2_CLASSIFICATION_FAILED_NO_FALLBACK','live_enabled':False}
    def confirm(self,identity,current_input):
        """Aucune méthode de transport n'est appelée, même après redémarrage."""
        value=self._operation(identity);snapshot=self._fresh(value,current_input)
        require(value['state']=='DECIDED' and digest(value['decision'])==value['decision_sha256'],'A2_DECISION_UNAVAILABLE_OR_CORRUPT')
        supervisor=OfflineSupervisor(value['supervisor_path'],self.clock);financial=supervisor.snapshot()
        require(financial['campaign']['status']=='AUTHORIZED' and financial['operations'][identity]['state']=='RECONCILED','A2_FINANCE_UNSETTLED_OR_REVOKED')
        require(financial['operations'][identity]['request_sha256']==digest(value['request']) and financial['operations'][identity]['result_sha256']==value['response_fingerprint'],'A2_FINANCIAL_RESULT_BINDING')
        decision=value['decision'];validate_decision(decision,snapshot['packet']);module=decision['module']
        if module=='CLARIFICATION':return {'state':'CLARIFICATION','medical_generation_authorized':False}
        if module not in snapshot['requests']:return {'state':'CLARIFICATION','module':module,'reason':'CONTEXT_REQUIRED','medical_generation_authorized':False}
        target=snapshot['requests'][module];new_body=json.loads(target['input']);by_id={v['id']:v for v in snapshot['candidates']}
        if self.require_auto_decision:
            exact=self.cache.resolve(target,allow_cr=not bool(current_input.get('history_id')))
            if exact['CR']['decision']=='HIT':
                return {'state':'EXACT_CR','module':module,'plan':exact,'medical_generation_authorized':False,'live_enabled':False}
        docs=[];answers=[];rejections=[]
        for row in decision['comparisons']:
            candidate=by_id[row['candidate_id']];old_body=candidate['context']
            if candidate['kind']=='CR' and row['relation']=='FULL_EQUIVALENCE':
                compatible=(candidate['module']==module and row['context_compatible']
                    and (self.qualification or canonical_question(old_body['question'])==canonical_question(new_body['question']) and sensitive_facts(old_body['question'])==sensitive_facts(new_body['question']))
                    and {k:v for k,v in old_body.items() if k!='question'}=={k:v for k,v in new_body.items() if k!='question'}
                    and candidate['original_request']['instructions']==target['instructions'])
                if compatible:answers.append(candidate)
                else:rejections.append({'id':candidate['id'],'reason':'TECHNICAL_GUARDS_REFUSED_SEMANTIC_PROPOSAL'})
            elif candidate['kind']=='CD' and row['relation']=='DOCUMENT_RELEVANT' and row['context_compatible']:
                a=old_body.get('profile',{});b=new_body.get('profile',{});same_known=all(not a.get(k) or not b.get(k) or a[k]==b[k] for k in set(a)|set(b))
                same_known=same_known and all(not old_body.get(k) or not new_body.get(k) or old_body[k]==new_body[k] for k in ('provided_renal_function','patient_draft','personal_preferences'))
                old=sensitive_facts(old_body['question']);new=sensitive_facts(new_body['question'])
                facts=all(not old[k] or not new[k] or old[k]==new[k] for k in old)
                with self.store.tx() as db:policy=self.cache._policies(db)['modules'][module]['CD']
                if same_known and facts and policy['enabled'] and 0<=self.clock()-candidate['created_at']<policy['ttl_days']*86400:
                    docs.append({'entry_id':candidate['id'],'row_sha256':candidate['row_sha256'],**candidate['document'],
                                 'semantic_decision_id':identity,'restriction':'Pertinence proposée ; applicabilité clinique non attestée. Aucune association incertaine affirmée.'})
                else:rejections.append({'id':candidate['id'],'reason':'PYTHON_DOCUMENT_CONTEXT_CONFLICT'})
        result={'state':'CD_ONLY' if docs else 'MISS','module':module,'documents':docs,'rejections':rejections,'medical_generation_authorized':False,'live_enabled':False,
                'python_validation_scope':'STRUCTURE_LITERAL_QUOTES_EXPLICIT_CONTEXT_AND_INTEGRITY_ONLY','medical_equivalence_proven_by_python':False}
        if answers:
            candidate=sorted(answers,key=lambda v:(-v['created_at'],v['id']))[0]
            plan=self.cache.resolve(candidate['original_request']);require(plan['CR']['decision']=='HIT' and plan['CR']['entry_id']==candidate['id'],'A2_FINAL_INTEGRITY_REFUSED')
            result.update(state='TEST_SEMANTIC_CR_HIT',display=plan['display'],source_entry_id=candidate['id'],original_question=candidate['context']['question'],new_question=new_body['question'],semantic_decision_id=identity,equivalence_profile='LUNA_EQUIVALENCE_NATIVE_F3_V1' if self.qualification else 'A2_STRICT_V1')
        with self.store.tx() as db:self._event(db,result['state'],identity)
        return result

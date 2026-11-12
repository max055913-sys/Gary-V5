"""Présélection lexicale SQLite, sans index vectoriel ou moteur RAG."""
from copy import deepcopy
import json
from .documentary_cache import DocumentaryCache,VERSION as CACHE_VERSION
from .generation_contract import build_request
from .live_supervisor import prepare_live_request
from .sol_web_profile import apply as apply_web_profile,VERSION as WEB_VERSION,TTT_VERSION,SUIVI_VERSION,PARAMETERS as WEB_PARAMETERS,LEGACY_VERSION as WEB_LEGACY_VERSION,validate as validate_web_profile,LEGACY_PARAMETERS as WEB_LEGACY_PARAMETERS
from .settings import Settings
from .storage import canonical,digest
from .functional_store import privacy_check
from .semantic_contract import lexical


class LocalCandidates:
    def __init__(self,cache):self.cache=cache;self.store=cache.store
    def rebuild(self,context):
        request=build_request(context['question'],context['module'],context.get('profile',{}),Settings(self.store).read_write(),context['documentary_depth'],context['context_policy'])
        request['input']=canonical(context)
        profile=context.get('documentary_web_profile')
        if profile in (WEB_VERSION,WEB_LEGACY_VERSION,TTT_VERSION,SUIVI_VERSION):
            # Le contexte persistant identifie le producteur ; ne jamais rabattre
            # un profil natif sur le transport historique plus restrictif.
            result=apply_web_profile(request)
            if profile==WEB_LEGACY_VERSION:
                result.update(deepcopy(WEB_LEGACY_PARAMETERS));result['input']=canonical(context)
            elif profile==WEB_VERSION:
                result.update(deepcopy(WEB_PARAMETERS));result['input']=canonical(context)
            if not validate_web_profile(result):raise ValueError('CANDIDATE_WEB_PROFILE_INVALID')
            return result
        if profile is not None:raise ValueError('CANDIDATE_WEB_PROFILE_UNKNOWN')
        return prepare_live_request(request)
    def register_context(self,request):
        """Métadonnées de contexte pour CD seuls ; aucun texte documentaire copié."""
        plan=self.cache.resolve(request,allow_cr=False);_,body=self.cache._base(request)
        for doc in plan['dependencies']:
            with self.store.tx() as db:
                original,h,created=self.cache._row(db,doc['id'],'CD')
                if h!=doc['sha256']:continue
                v={'schema':'gary_a2_context_index_v1','created_at':created,'test':self.cache.test,'entry_id':doc['id'],'entry_sha256':h,'context':body}
                self.cache._put(db,'A2_CONTEXT_V1',v,'A2_CONTEXT_'+digest([doc['id'],h]))
    def collect(self,target_requests,limit=12,*,include_zero=False):
        if include_zero and not self.cache.test:raise ValueError('A2_CANDIDATE_PROFILE_UNQUALIFIED')
        contexts={};raw={}
        with self.store.tx() as db:
            rows=db.execute("SELECT id FROM entries WHERE kind IN ('CR','A2_CONTEXT_V1') ORDER BY created DESC,id DESC LIMIT 500").fetchall()
            for (identity,) in rows:
                try:
                    v,h,created=self.cache._row(db,identity)
                    if v.get('test') is not self.cache.test:continue
                    if identity.startswith('CR_') and v.get('schema')==CACHE_VERSION:
                        contexts[digest(v['context'])]=v['context'];raw[identity]=(v,h,created)
                    elif v.get('schema')=='gary_a2_context_index_v1':contexts[digest(v['context'])]=v['context']
                except (ValueError,KeyError,TypeError,OSError):continue
        found={}
        for context in contexts.values():
            try:
                original=self.rebuild(context);module=context['module']
                if module not in target_requests:continue
                privacy_check(context)
                plan=self.cache.resolve(original)
                if plan['CR']['decision']=='HIT':
                    identity=plan['CR']['entry_id']
                    if identity in raw:
                        v,h,c=raw[identity];found[identity]={'id':identity,'kind':'CR','module':module,'row_sha256':h,'context':deepcopy(context),'text':v['display']['text'],'original_request':original,'created_at':c}
                docs=self.cache.resolve(original,allow_cr=False)
                for ref,item in zip(docs['dependencies'],docs['documents']):
                    identity=ref['id']
                    with self.store.tx() as db:v,h,c=self.cache._row(db,identity,'CD')
                    if h!=ref['sha256']:continue
                    text=item['excerpt'] if item['excerpt'] is not None else canonical({'title':item['title'],'url':item['url']})
                    found[identity]={'id':identity,'kind':'CD','module':module,'row_sha256':h,'context':deepcopy(context),'text':text,'document':item,'original_request':original,'created_at':c}
            except (ValueError,KeyError,TypeError,OSError):continue
        ranked=[]
        for value in found.values():
            # Limite entière : jamais couper un avertissement, une dose ou une durée.
            if len(value['text'])>12000:continue
            target=json.loads(target_requests[value['module']]['input']);query=lexical(target['question'])
            words=lexical(value['context']['question']+' '+value['text']);score=len(query&words)/max(1,len(query|words))
            if score==0 and not include_zero:continue
            value['score']=score;ranked.append(value)
        ranked.sort(key=lambda v:(-v['score'],v['id']))
        return ranked[:limit]

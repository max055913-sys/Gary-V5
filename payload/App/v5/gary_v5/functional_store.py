"""Historique et brouillons : entrées versionnées dans la SQLite V5 existante.

Aucun cache CD/CR parallèle. Aucun appel fournisseur. Les suppressions concernent
uniquement la vue historique demandée, jamais les preuves ou registres financiers.
"""
from copy import deepcopy
from datetime import datetime,timezone
import json
import re
import time
import uuid
from .storage import canonical,digest
from .commercial_supervisor import require
from .module_rules import RULES

def utc():return datetime.now(timezone.utc).isoformat()
def patient_document_title(source,fallback):
    fence=None
    for line in source.splitlines():
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$',line)
        if marker:
            run,tail=marker.groups()
            if fence is None:fence=run
            elif run[0]==fence[0] and len(run)>=len(fence) and not tail.strip():fence=None
            continue
        if fence is None and (heading:=re.match(r'^ {0,3}#[ \t]+(.+)$',line)):
            title=re.sub(r'[ \t]+#+[ \t]*$','',heading[1]).strip()
            if title:return title
    return fallback

def text(v,maximum):
    require(type(v) is str and len(v)<=maximum and not re.search(r'\bsk-[A-Za-z0-9_-]{16,}',v),'LOCAL_TEXT_INVALID_OR_SECRET')
    return v

def privacy_check(value):
    """Refus conservateur de quelques identifiants explicites ; jamais exhaustif.

    Aucun contenu détecté n'est journalisé. Pas de conclusion d'anonymisation.
    """
    raw=value if isinstance(value,str) else canonical(value)
    patterns=(r'\bsk-[A-Za-z0-9_-]{16,}',r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
              r'\b(?:0[1-9](?:[ .-]?\d{2}){4}|\+33[ .-]?[1-9](?:[ .-]?\d{2}){4})\b',
              r'\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2])\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b',
              r'\b(?:nom(?:\s+du\s+patient)?|prénom|prenom|date\s+de\s+naissance|adresse\s+(?:du\s+patient|personnelle))\s*["\']?\s*:\s*["\']?\s*[^\s"\'}]',
              r'\bpatient(?:e)?\s+(?:M\.|Mme|Monsieur|Madame)\s+\w+')
    require(not any(re.search(p,raw,re.I) for p in patterns),'POTENTIALLY_IDENTIFYING_DATA_REFUSED')

class FunctionalStore:
    def __init__(self,store):self.store=store
    def load(self,db,identity,kind):
        row=db.execute('SELECT payload,sha FROM entries WHERE id=? AND kind=?',(identity,kind)).fetchone()
        require(row is not None,'LOCAL_ENTRY_ABSENT')
        try:value=json.loads(row[0])
        except ValueError:raise ValueError('FUNCTIONAL_DATA_CORRUPT') from None
        require(type(value) is dict and digest(value)==row[1],'FUNCTIONAL_DATA_CORRUPT')
        return value
    def write(self,db,identity,kind,value):
        db.execute('INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?)',(identity,kind,canonical(value),digest(value),time.time()))
    def options(self,value=None,revision=None):
        defaults={'schema':'gary_workspace_v1','revision':0,'font_size':15,'history_enabled':False,'personal_suivi':'','context_policy':'intermediaire'}
        with self.store.tx() as db:
            exists=db.execute("SELECT 1 FROM entries WHERE id='workspace_v1' AND kind='WORKSPACE_V1'").fetchone()
            old=self.load(db,'workspace_v1','WORKSPACE_V1') if exists else defaults
            if value is None:return deepcopy(old)
            require(type(revision) is int and revision==old['revision'],'REVISION_CONFLICT')
            require(type(value) is dict and set(value)==set(defaults) and value['schema']==defaults['schema'],'WORKSPACE_INVALID')
            require(type(value['font_size']) is int and 14<=value['font_size']<=18 and type(value['history_enabled']) is bool,'WORKSPACE_INVALID')
            text(value['personal_suivi'],5000);require(value['context_policy'] in ('court','intermediaire','riche'),'WORKSPACE_INVALID')
            value=deepcopy(value);value['revision']=old['revision']+1;self.write(db,'workspace_v1','WORKSPACE_V1',value);return value
    def record(self,request,display,state,*,history_id=None,test=False,evidence=None):
        data=json.loads(request['input']);require(data['module'] in RULES,'MODULE_INVALID')
        text(data['question'],1000)
        require(type(display) is dict and type(display.get('text')) is str,'HISTORY_DISPLAY_INVALID')
        text(display['text'],1_000_000)
        text(canonical(data),2_000_000);text(canonical(display),2_000_000)
        privacy_check(data);privacy_check(display)
        with self.store.tx() as db:
            if history_id:
                old=self.load(db,history_id,'HISTORY_V1')
                previous=old['versions'][-1]
                require(previous['question']==data['question'] and previous['module']==data['module'],'HISTORY_REFRESH_SCOPE_MISMATCH')
            else:
                history_id='h_'+uuid.uuid4().hex
                old={'schema':'gary_history_v1','id':history_id,'revision':0,'created_at':utc(),'versions':[]}
            version={'id':'v_'+uuid.uuid4().hex,'created_at':utc(),'question':data['question'],'module':data['module'],
                     'profile':deepcopy(data.get('profile',{})),'depth':data.get('documentary_depth'),
                     'additional_context':{k:deepcopy(data[k]) for k in ('personal_preferences','provided_renal_function','patient_draft','rewrite_instruction') if k in data},
                     'context_policy':data.get('context_policy'),'state':state,'test':test,
                     'request_sha256':digest(request),'display':deepcopy(display),'evidence':str(evidence) if evidence else None}
            old['versions'].append(version);old['revision']+=1;self.write(db,history_id,'HISTORY_V1',old)
            return {'history_id':history_id,'version_id':version['id'],'created_at':version['created_at']}
    def history(self,identity):
        with self.store.tx() as db:return self.load(db,identity,'HISTORY_V1')
    def histories(self,query='',module=''):
        text(query,1000);require(not module or module in RULES,'MODULE_INVALID')
        with self.store.tx() as db:
            ids=[r[0] for r in db.execute("SELECT id FROM entries WHERE kind='HISTORY_V1' ORDER BY created DESC,id")]
            result=[]
            for identity in ids:
                h=self.load(db,identity,'HISTORY_V1');v=h['versions'][-1]
                if module and v['module']!=module:continue
                if query.casefold() not in (v['question']+' '+v['display']['text']).casefold():continue
                result.append({'id':identity,'revision':h['revision'],'versions':len(h['versions']),**{k:v[k] for k in ('question','module','created_at','state','test')}})
            return result
    def delete_history(self,identity,revision,confirmed):
        require(confirmed is True,'DELETE_CONFIRMATION_REQUIRED')
        with self.store.tx() as db:
            value=self.load(db,identity,'HISTORY_V1');require(type(revision) is int and revision==value['revision'],'REVISION_CONFLICT')
            db.execute("DELETE FROM entries WHERE id=? AND kind='HISTORY_V1'",(identity,))
            db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('HISTORY_DELETED',identity,time.time()))
        return {'deleted':True,'evidence_preserved':True}
    def purge_history(self,count,confirmed):
        require(confirmed is True,'DELETE_CONFIRMATION_REQUIRED')
        with self.store.tx() as db:
            actual=db.execute("SELECT COUNT(*) FROM entries WHERE kind='HISTORY_V1'").fetchone()[0]
            require(type(count) is int and actual==count,'REVISION_CONFLICT')
            db.execute("DELETE FROM entries WHERE kind='HISTORY_V1'")
            db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('HISTORY_PURGED',str(actual),time.time()))
        return {'deleted_count':actual,'evidence_preserved':True}
    def create_draft(self,title,content,*,sources=None,source_key=None,test=False):
        text(title,1000);text(content,100000)
        text(canonical(sources or []),1_000_000)
        privacy_check(content);privacy_check(sources or [])
        identity='d_'+(digest(source_key)[:32] if source_key else uuid.uuid4().hex)
        with self.store.tx() as db:
            if db.execute("SELECT 1 FROM entries WHERE id=? AND kind='DRAFT_V1'",(identity,)).fetchone():return self.load(db,identity,'DRAFT_V1')
            value={'schema':'gary_patient_draft_v1','id':identity,'title':title,'revision':1,'created_at':utc(),
                   'test':test,'sources':deepcopy(sources or []),'origin':deepcopy(source_key),'validation':None,'approvals':[],
                   'versions':[{'revision':1,'text':content,'text_sha256':digest(content),'created_at':utc()}]}
            self.write(db,identity,'DRAFT_V1',value);return value
    def draft(self,identity):
        with self.store.tx() as db:return self.active_draft(db,identity)
    def active_draft(self,db,identity):
        draft=self.load(db,identity,'DRAFT_V1')
        require(not draft.get('deleted_at'),'DRAFT_DELETED')
        return draft
    def drafts(self,*,deleted=False):
        with self.store.tx() as db:
            values=[self.load(db,r[0],'DRAFT_V1') for r in db.execute("SELECT id FROM entries WHERE kind='DRAFT_V1' ORDER BY created DESC")]
            return [{**{k:v[k] for k in ('id','title','revision','created_at','test','validation')},
                     'visibility_revision':v.get('visibility_revision',0),
                     'document_title':patient_document_title(v['versions'][-1]['text'],v['title'])}
                    for v in values if bool(v.get('deleted_at'))==deleted]
    def set_draft_deleted(self,identity,revision,visibility_revision,confirmed,*,deleted):
        require(type(identity) is str and re.fullmatch(r'd_[0-9a-f]{32}',identity),'DRAFT_ID_INVALID')
        require(confirmed is True,'DRAFT_VISIBILITY_CONFIRMATION_REQUIRED')
        with self.store.tx() as db:
            draft=self.load(db,identity,'DRAFT_V1')
            version=draft.get('visibility_revision',0)
            require(type(revision) is int and revision==draft['revision'] and type(visibility_revision) is int
                    and visibility_revision==version and bool(draft.get('deleted_at'))!=deleted,'REVISION_CONFLICT')
            draft['deleted_at']=utc() if deleted else None
            draft['visibility_revision']=version+1
            self.write(db,identity,'DRAFT_V1',draft)
            return {'id':identity,'deleted':deleted}
    def save_draft(self,identity,revision,content):
        text(content,100000)
        privacy_check(content)
        with self.store.tx() as db:
            v=self.active_draft(db,identity);require(type(revision) is int and v['revision']==revision,'REVISION_CONFLICT')
            if v['versions'][-1]['text']==content:return v
            v['revision']+=1;v['validation']=None
            v['versions'].append({'revision':v['revision'],'text':content,'text_sha256':digest(content),'created_at':utc()})
            self.write(db,identity,'DRAFT_V1',v);return v
    def approve_draft(self,identity,revision,validator,confirmed):
        text(validator,200);require(confirmed is True and validator.strip(),'DOCTOR_APPROVAL_REQUIRED')
        with self.store.tx() as db:
            v=self.active_draft(db,identity);require(type(revision) is int and v['revision']==revision,'REVISION_CONFLICT')
            require(bool(v['versions'][-1]['text'].strip()),'EMPTY_DRAFT')
            v['validation']={'method':'USER_EXPLICIT_DOCUMENT_APPROVAL','validator':validator.strip(),'created_at':utc(),
                             'revision':revision,'text_sha256':v['versions'][-1]['text_sha256'],'test':v['test']}
            v.setdefault('approvals',[]).append(deepcopy(v['validation']))
            db.execute("INSERT OR REPLACE INTO metadata VALUES('last_fich_validator_v1',?)",(v['validation']['validator'],))
            self.write(db,identity,'DRAFT_V1',v);return v
    def last_validator(self):
        with self.store.tx() as db:
            row=db.execute("SELECT value FROM metadata WHERE key='last_fich_validator_v1'").fetchone()
            if row:return row[0]
            latest=None
            for (identity,) in db.execute("SELECT id FROM entries WHERE kind='DRAFT_V1'"):
                draft=self.load(db,identity,'DRAFT_V1')
                for approval in draft.get('approvals') or ([draft['validation']] if draft.get('validation') else []):
                    if latest is None or approval['created_at']>latest['created_at']:latest=approval
            return latest['validator'] if latest else ''
    def require_approved(self,identity,revision):
        v=self.draft(identity);a=v['validation']
        require(type(revision) is int and v['revision']==revision and a is not None and a['revision']==revision
                and a['text_sha256']==digest(v['versions'][-1]['text']),'DRAFT_NOT_APPROVED')
        return v
    @staticmethod
    def approved_version(draft,revision):
        require(type(revision) is int,'DRAFT_NOT_APPROVED')
        version=next((v for v in draft['versions'] if v['revision']==revision),None)
        approvals=draft.get('approvals',[])+([draft['validation']] if draft.get('validation') else [])
        require(version is not None and version['text_sha256']==digest(version['text']),'DRAFT_NOT_APPROVED')
        approval=next((a for a in reversed(approvals) if a.get('revision')==revision
                       and a.get('text_sha256')==version['text_sha256']
                       and a.get('method')=='USER_EXPLICIT_DOCUMENT_APPROVAL'
                       and isinstance(a.get('validator'),str) and a['validator'].strip()
                       and a.get('created_at') and a.get('test') is draft['test']),None)
        require(approval is not None,'DRAFT_NOT_APPROVED')
        return {**draft,'revision':revision,'validation':approval,'versions':[version]}

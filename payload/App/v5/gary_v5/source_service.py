"""Service E1 bis : états d'accès, preuves locales, pont CD et contexte sans IA."""
from copy import deepcopy
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
import hashlib,json,re,time,uuid
from urllib.parse import urlsplit
from .source_catalog import SourceCatalog,source_policy,professional,KEY
from .public_acquisition import PublicFetcher,public_url,MAX_BYTES
from .documentary_cache import DocumentaryCache,bytes_sha,iso
from .functional_store import privacy_check
from .commercial_supervisor import require
from .storage import canonical,digest

class NativeHTML(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.stack=[];self.parts=[];self.preferred=[];self.title=[];self.auth=False;self.password=False;self.tables=0;self.complex=False
 def handle_starttag(self,tag,attrs):
  require(len(self.stack)<256,'WEB_HTML_DEPTH_LIMIT')
  a=dict(attrs)
  if tag=='input' and a.get('type','').casefold()=='password':
   self.password=True
   if any(t in ('main','article') for t,h in self.stack) and not any(h for t,h in self.stack if t!='form'):self.auth=True
  if tag=='table':self.tables+=1
  if tag in ('svg','math','sup','sub','iframe'):self.complex=True
  # Une illustration ou note latérale dans le contenu peut porter une condition :
  # ne pas publier le seul texte restant comme si ce contexte avait été acquis.
  if tag in ('aside','img') and any(t in ('main','article') for t,h in self.stack):self.complex=True
  hidden=tag in ('script','style','nav','header','footer','form','aside','table','svg','math','iframe','template','noscript') or 'hidden' in a or a.get('aria-hidden')=='true' or bool(re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)',a.get('style',''),re.I))
  if tag not in ('br','hr','meta','link','img','input','source','wbr','area','base','embed','param','track','col'):
   self.stack.append((tag,hidden))
  if tag in ('p','div','li','br','h1','h2','h3','h4','h5','section','article','main'):self.handle_data('\n')
 def handle_endtag(self,tag):
  if tag in ('p','div','li','h1','h2','h3','h4','h5','section','article','main'):self.handle_data('\n')
  for i in range(len(self.stack)-1,-1,-1):
   if self.stack[i][0]==tag:self.stack=self.stack[:i];break
 def handle_data(self,data):
  require(len(self.parts)<50000,'WEB_HTML_COMPLEXITY_LIMIT')
  if any(t=='title' for t,h in self.stack):self.title.append(data);return
  if any(h for t,h in self.stack):return
  self.parts.append(data)
  if any(t in ('main','article') for t,h in self.stack):self.preferred.append(data)
 def text(self):
  preferred=''.join(self.preferred);value=preferred if len(preferred.strip())>=80 else ''.join(self.parts)
  return '\n'.join(v for v in (re.sub(r'[\t \r\f]+',' ',s).strip() for s in value.split('\n')) if v)

class SourceService:
 def __init__(self,store,*,fetcher=None):
  self.store=store;self.catalog=SourceCatalog(store);self.cache=DocumentaryCache(store)
  require(fetcher is None or self.cache.test,'WEB_FIXTURE_OFFLINE_ONLY');self.fixture=fetcher is not None;self.fetcher=fetcher or PublicFetcher()
 def read(self):
  env=self.catalog.read();latest={}
  for row in self.store.rows('WEB_CHECK_V1')[:200]:
   job=row['data'];identity=job['source']['id']
   if identity not in latest:
    same=job.get('protocol_sha256')==self.protocol() and any(s['id']==identity and source_policy(s)==job['policy'] for s in env['value']['sources'])
    latest[identity]=job.get('result',{'status':'ERREUR','reason':'INTERRUPTED_NO_AUTO_RETRY'}) if same else {'status':'NON_VERIFIEE','reason':'CONFIGURATION_CHANGED'}
  return {**env,'latest':latest,'authentication':{'available':False,'phase':'E1_TER_NOT_STARTED'}}
 def probe(self,identity,nonce):
  return self._probe(self.catalog.source(identity),nonce,'CONFIGURED')
 def probe_complementary(self,source,nonce,prior_results,coverage,*,request=None):
  """Connecteur serveur, pas un booléen navigateur ni une recherche systématique."""
  require(type(source) is dict and set(source)=={'title','url','module','rights_evidence','automation_allowed','local_reuse_allowed','external_ai_allowed'},'WEB_COMPLEMENT_SCHEMA')
  url=public_url(source['url']);require(type(source['title']) is str and 0<len(source['title'])<=300,'WEB_COMPLEMENT_TITLE_OR_MODULE')
  from .module_rules import RULES
  require(source['module'] in RULES and type(source['rights_evidence']) is str and len(source['rights_evidence'])<=1000,'WEB_COMPLEMENT_RIGHTS')
  require(type(prior_results) is list and 0<len(prior_results)<=20,'WEB_PRIOR_EVIDENCE_REQUIRED')
  confirmed=[]
  for result in prior_results:
   require(type(result) is dict and type(result.get('id')) is str,'WEB_PRIOR_EVIDENCE_REQUIRED')
   with self.store.tx() as db:prior,_,_=self.cache._row(db,result['id'],'WEB_CHECK_V1')
   require(prior['state']=='COMPLETE' and prior.get('origin')=='CONFIGURED' and source['module'] in prior['source']['modules'] and prior.get('protocol_sha256')==self.protocol(),'WEB_PRIOR_EVIDENCE_REQUIRED')
   require(source_policy(self.catalog.source(prior['source']['id']))==prior['policy'],'WEB_PRIOR_EVIDENCE_REQUIRED')
   confirmed.append(prior['result'])
  from .sol_documentary_contracts import SolCoverageRegistry
  require(type(request) is dict and json.loads(request['input'])['module']==source['module'],'WEB_COVERAGE_REQUEST_REQUIRED')
  recognized=SolCoverageRegistry(self.store).recognize(coverage,request,self._coverage_observations(request,prior_results))
  require(complement_decision(confirmed,recognized)['expand'],'WEB_COMPLEMENT_NOT_JUSTIFIED')
  require(all(type(source[k]) is bool for k in ('automation_allowed','local_reuse_allowed','external_ai_allowed')),'WEB_FLAGS');privacy_check(source)
  require(not re.search(r'(?:password|mot de passe|cookie|authorization|bearer|token|jeton)\s*[:=]',canonical(source),re.I),'WEB_SECRET_FIELDS_REFUSED')
  env=self.catalog.read();require(not env['preferences_diverged'],'WEB_PREFERENCES_CHANGED')
  require(not any(s['url']==url for s in env['value']['sources']),'WEB_COMPLEMENT_ALREADY_CONFIGURED')
  with self.store.tx() as db:require(db.execute("SELECT 1 FROM metadata WHERE key=?",(KEY,)).fetchone() is not None,'WEB_CATALOG_SAVE_REQUIRED')
  candidate={'id':'complement_'+digest(source)[:24],'title':source['title'],'url':url,'domain':urlsplit(url).hostname,'modules':{source['module']:1},'enabled':True,'access_kind':'UNKNOWN',**{k:source[k] for k in ('rights_evidence','automation_allowed','local_reuse_allowed','external_ai_allowed')}}
  return self._probe(candidate,nonce,'COMPLEMENTARY',coverage)
 def _coverage_observations(self,request,prior_results):
  from .request_policy import valid_application_request
  require(valid_application_request(request,standard=True),'WEB_STANDARD_REQUEST_REQUIRED')
  require(type(prior_results) is list and 0<len(prior_results)<=20,'WEB_PRIOR_EVIDENCE_REQUIRED')
  module=json.loads(request['input'])['module'];observations=[];seen=set()
  for result in prior_results:
   require(type(result) is dict and type(result.get('id')) is str and result['id'] not in seen,'WEB_PRIOR_EVIDENCE_REQUIRED');seen.add(result['id'])
   with self.store.tx() as db:job,h,_=self.cache._row(db,result['id'],'WEB_CHECK_V1')
   require(job['state']=='COMPLETE' and job.get('origin')=='CONFIGURED' and module in job['source']['modules'] and job.get('protocol_sha256')==self.protocol(),'WEB_PRIOR_EVIDENCE_REQUIRED')
   require(source_policy(self.catalog.source(job['source']['id']))==job['policy'],'WEB_PRIOR_EVIDENCE_REQUIRED')
   require(self.read()['latest'].get(job['source']['id'],{}).get('id')==result['id'],'WEB_COVERAGE_SOURCE_SUPERSEDED')
   with self.store.tx() as db:current=self.cache._source(db,job['source']['url'])
   require(not current or current['validity']!='REVOKED','WEB_COVERAGE_SOURCE_REVOKED')
   r=job['result'];observations.append({'id':result['id'],'job_sha256':h,'source_id':job['source']['id'],'policy_sha256':job['policy'],
     'url':r.get('final_url',job['source']['url']),'checked_at':r['checked_at'],'status':r['status'],'reason':r['reason'],
     'raw_sha256':r.get('response_sha256'),'native_text_sha256':r.get('native_text_sha256'),'version_sha256':job.get('manifest_sha256'),
     'excerpt':self.read_text(result['id'])['text'] if r.get('cd_eligible') else None,
     'content_scope':'NATIVE_TEXT_ONLY' if r.get('cd_eligible') else 'NO_ADMISSIBLE_EXCERPT'})
  return observations
 def prepare_coverage(self,request,prior_results):
  from .sol_documentary_contracts import SolCoverageRegistry
  return SolCoverageRegistry(self.store).prepare(request,self._coverage_observations(request,prior_results))
 def _probe(self,source,nonce,origin,assessment_reference=None):
  # Transport historique conservé uniquement pour les fixtures hors réseau.
  require(source['access_kind'] not in ('AUTHENTICATED','SUBSCRIPTION','RESTRICTED','API','OTHER'),'WEB_PROFESSIONAL_ACCESS_ARCHIVED')
  require(self.fixture,'WEB_PUBLIC_NATIVE_SOL_REQUIRED')
  require(type(nonce) is str and re.fullmatch(r'[a-f0-9-]{32,36}',nonce),'WEB_CHECK_ID')
  identity=source['id'];require(source['enabled'],'WEB_SOURCE_DISABLED');require(source['url'] is not None,'WEB_URL_ABSENT')
  jobid='WEB_CHECK_'+nonce;job={'created_at':time.time(),'schema':'gary_web_check_v1','source':source,'origin':origin,'assessment_reference':assessment_reference,'catalog_sha256':digest(self.catalog.read()['value']),'policy':source_policy(source),'protocol_sha256':self.protocol(),'state':'FETCHING'}
  with self.store.tx() as db:
   row=db.execute('SELECT 1 FROM entries WHERE id=?',(jobid,)).fetchone()
   if row:
    prior=self.cache._row(db,jobid,'WEB_CHECK_V1')[0];require(prior['policy']==job['policy'] and prior.get('protocol_sha256')==job['protocol_sha256'],'WEB_CHECK_SCOPE_CHANGED')
    return prior.get('result',{'status':'ERREUR','reason':'IN_PROGRESS_OR_INTERRUPTED_NO_RETRY'})
   if not self.fixture:
    for (recent,) in db.execute("SELECT id FROM entries WHERE kind='WEB_CHECK_V1' AND created>?",(time.time()-10,)).fetchall():
     previous=self.cache._row(db,recent,'WEB_CHECK_V1')[0]
     require(urlsplit(previous['source']['url']).hostname!=urlsplit(source['url']).hostname,'WEB_RATE_LIMIT')
   # Pas de file de téléchargements sans limite : quatre acquisitions simultanées maximum.
   active=db.execute("SELECT COUNT(*) FROM entries WHERE kind='WEB_CHECK_V1' AND created>? AND payload LIKE ?",(time.time()-20,'%\"state\":\"FETCHING\"%')).fetchone()[0]
   require(active<4,'WEB_CHECK_BUSY');self.cache._put(db,'WEB_CHECK_V1',job,jobid)
  result={'id':jobid,'source_id':identity,'origin':origin,'checked_at':iso(time.time()),'status':'ERREUR','page_retrieved':False,'text_extracted':False,'cd_eligible':False,'reason':'UNAVAILABLE','characters':0}
  try:
   url=public_url(source['url']);response=self.fetcher.fetch(url)
   require(type(response) is dict and type(response['body']) is bytes and len(response['body'])<=MAX_BYTES,'WEB_RESPONSE_INVALID')
   final=public_url(response['url']);require(urlsplit(final).hostname==urlsplit(url).hostname,'WEB_CROSS_HOST_REQUIRES_REVIEW')
   status=response['status'];result.update(http_status=status,final_url=final)
   if status in (401,407):result.update(status='AUTHENTIFICATION_NECESSAIRE',reason='LOGIN_REQUIRED')
   elif status in (403,429,451):result.update(status='ACCES_RESTREINT',reason='ACCESS_DENIED_OR_RATE_LIMITED')
   elif status!=200:result.update(status='CONTENU_INDISPONIBLE',reason='HTTP_NO_PAGE')
   else:
    result.update(page_retrieved=True,response_sha256=hashlib.sha256(response['body']).hexdigest(),content_type=response['content_type']);kind=response['content_type'].split(';')[0].strip()
    require(kind in ('text/html','text/plain'),'WEB_CONTENT_TYPE_UNSUPPORTED')
    charset=re.search(r'charset\s*=\s*["\']?([a-zA-Z0-9_-]+)',response['content_type']);encoding=charset[1] if charset else 'utf8'
    require(encoding.lower() in ('utf8','utf-8','iso-8859-1','windows-1252'),'WEB_CHARSET_UNSUPPORTED')
    raw=response['body'].decode(encoding,errors='strict');parser=NativeHTML()
    if kind=='text/html':parser.feed(raw);parser.close();text=parser.text()
    else:text=raw
    result.update(characters=len(text),text_extracted=bool(text.strip()),title=''.join(parser.title).strip()[:300] or source['title'],table_count=parser.tables,coverage='NOT_EVALUATED')
    result['native_text_sha256']=hashlib.sha256(text.encode('utf8')).hexdigest()
    privacy_check({'title':result['title']})
    require(not re.search(r'(?:password|mot de passe|cookie|authorization|bearer|token|jeton)\s*[:=]',result['title'],re.I),'WEB_SECRET_CONTENT_REFUSED')
    login=parser.auth or (parser.password and len(text.strip())<80) or bool(re.search(r'vous devez vous connecter|connectez-vous pour acc[eé]der|abonnez-vous pour',text[:2000],re.I))
    if login:result.update(status='AUTHENTIFICATION_NECESSAIRE',reason='LOGIN_PAGE_NOT_MEDICAL_CONTENT')
    elif len(text.strip())<80:result.update(status='CONTENU_INDISPONIBLE',reason='EMPTY_OR_INSUFFICIENT_NATIVE_TEXT')
    else:
     result.update(status='ACCESSIBLE',reason='NATIVE_TEXT_AVAILABLE_NOT_CLINICALLY_VALIDATED')
     rights=source['automation_allowed'] and source['local_reuse_allowed']
     admissible=rights and not professional(urlsplit(url).hostname) and not parser.tables and not parser.complex
     if professional(urlsplit(url).hostname):result['reason']='PROFESSIONAL_ACCESS_AND_RIGHTS_NOT_QUALIFIED'
     elif parser.tables or parser.complex:result['reason']='STRUCTURAL_REVIEW_REQUIRED'
     elif not rights:result['reason']='RIGHTS_NOT_QUALIFIED_FOR_CD_AND_AI'
     if admissible:
      require(len(text)<=90000,'WEB_TEXT_LIMIT_NO_TRUNCATION')
      require(not re.search(r'(?:password|mot de passe|cookie|authorization|bearer|token|jeton)\s*[:=]',text,re.I),'WEB_SECRET_CONTENT_REFUSED');privacy_check(text)
      if origin=='CONFIGURED':require(source_policy(self.catalog.source(identity))==job['policy'],'WEB_POLICY_CHANGED')
      else:require(digest(self.catalog.read()['value'])==job['catalog_sha256'],'WEB_POLICY_CHANGED')
      folder=self.snapshot_folder(uuid.uuid4().hex);folder.mkdir(parents=True)
      data=text.encode('utf8');(folder/'source.txt').write_bytes(data)
      updated=None
      if response.get('last_modified'):
       try:updated=parsedate_to_datetime(response['last_modified']).isoformat()
       except (ValueError,TypeError):pass
      manifest={'schema':'gary_cd_snapshot_v1','test':self.cache.test,'url':final,'title':result['title'],'publication_date':None,'updated_date':updated,'acquired_at':result['checked_at'],'reuse_rights':'TEST_ONLY' if self.cache.test else 'LOCAL_REUSE_ALLOWED','content_sha256':hashlib.sha256(data).hexdigest()}
      (folder/'manifest.json').write_text(canonical(manifest),encoding='utf8')
      evidence={'schema':'gary_acquisition_e1bis_v1','source_id':identity,'policy_sha256':job['policy'],'original_url':url,'final_url':final,'raw_sha256':hashlib.sha256(response['body']).hexdigest(),'text_sha256':manifest['content_sha256'],'content_type':response['content_type'],'parser_sha256':bytes_sha(Path(__file__)),'transport_sha256':bytes_sha(Path(__file__).with_name('public_acquisition.py')),'rights_basis':'USER_DECLARATION_NOT_INDEPENDENT_LEGAL_VALIDATION','rights_evidence':source['rights_evidence'],'rendering':'NATIVE_DOM_NO_JS_CSS_RENDER','redirects':response.get('redirects',[])}
      (folder/'acquisition.json').write_text(canonical(evidence),encoding='utf8')
      self._observe_version(final,text)
      job['snapshot']=folder.name;job['evidence_sha256']=bytes_sha(folder/'acquisition.json');job['manifest_sha256']=bytes_sha(folder/'manifest.json')
      result.update(local_snapshot=True,cd_eligible=source['external_ai_allowed'],reason='AUTHORIZED_NATIVE_SNAPSHOT_AVAILABLE' if source['external_ai_allowed'] else 'LOCAL_ONLY_NOT_AUTHORIZED_FOR_AI',snapshot_id=folder.name)
  except Exception as exc:
   result.pop('title',None)
   code=str(exc) if isinstance(exc,ValueError) and str(exc).startswith('WEB_') and re.fullmatch(r'[A-Z_]+',str(exc)) else 'WEB_ACQUISITION_FAILED'
   result.update(cd_eligible=False,status='ACCES_RESTREINT' if any(s in code for s in ('PRIVATE','ROBOTS','FORBIDDEN','REVIEW','HTTPS','SENSITIVE')) else 'ERREUR',reason=code)
  job.update(state='COMPLETE',result=result)
  with self.store.tx() as db:self.cache._put(db,'WEB_CHECK_V1',job,jobid);db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('WEB_CHECK_FINISHED',canonical({'id':jobid,'status':result['status']}),time.time()))
  return result
 def protocol(self):
  return digest({name:bytes_sha(Path(__file__).with_name(name)) for name in ('source_service.py','public_acquisition.py','source_catalog.py')})
 def snapshot_folder(self,name):
  require(type(name) is str and re.fullmatch('[a-f0-9]{32}',name),'WEB_SNAPSHOT_INVALID')
  folder=self.store.root/'cache_sources'/name
  for p in (folder,*folder.parents):require(not p.is_symlink() and not p.is_junction(),'WEB_PROOF_PATH_REFUSED')
  for name in ('source.txt','manifest.json','acquisition.json'):
   p=folder/name;require(not p.is_symlink() and not p.is_junction(),'WEB_PROOF_PATH_REFUSED')
  return folder
 def _observe_version(self,url,text):
  with self.store.tx() as db:
   current=self.cache._source(db,url)
   if not current or current['validity']!='ACTIVE' or current['content_kind']!='EXCERPT':return
   for (identity,) in db.execute("SELECT id FROM entries WHERE kind='CD' ORDER BY created DESC"):
    try:doc,_,_=self.cache._row(db,identity,'CD')
    except ValueError:continue
    if doc.get('url')==url and doc.get('source_version_sha256')==current['version_sha256']:
     if doc.get('excerpt')!=text:
      current.update(validity='REPLACED',observed_changed_at=time.time());self.cache._put(db,'CACHE_SOURCE_V1',current,'CACHE_SOURCE_'+digest(url))
     return
 def read_text(self,identity):
  with self.store.tx() as db:job,_,_=self.cache._row(db,identity,'WEB_CHECK_V1')
  require(job['state']=='COMPLETE' and job['result'].get('local_snapshot') and job.get('protocol_sha256')==self.protocol(),'WEB_TEXT_UNAVAILABLE')
  if job.get('origin')=='COMPLEMENTARY':require(digest(self.catalog.read()['value'])==job['catalog_sha256'],'WEB_SOURCE_POLICY_CHANGED')
  else:require(source_policy(self.catalog.source(job['source']['id']))==job['policy'],'WEB_SOURCE_POLICY_CHANGED')
  folder=self.snapshot_folder(job['snapshot']);require(bytes_sha(folder/'acquisition.json')==job['evidence_sha256'] and bytes_sha(folder/'manifest.json')==job['manifest_sha256'],'WEB_EVIDENCE_CHANGED')
  manifest=json.loads((folder/'manifest.json').read_text('utf8'));require(bytes_sha(folder/'source.txt')==manifest['content_sha256'],'WEB_EVIDENCE_CHANGED')
  return {'text':(folder/'source.txt').read_text('utf8'),'url':manifest['url'],'acquired_at':manifest['acquired_at'],'limitations':'Texte natif sans rendu JavaScript/CSS ; aucune validation clinique.'}
 def prepare_context(self,request,acquisitions):
  """Pont explicite serveur uniquement ; aucun transport Sol et aucun outil retiré."""
  from .request_policy import valid_application_request
  require(valid_application_request(request,standard=True),'WEB_STANDARD_REQUEST_REQUIRED')
  require(type(acquisitions) is list and len(acquisitions)<=20 and all(type(i) is str for i in acquisitions) and len(set(acquisitions))==len(acquisitions),'WEB_ACQUISITION_LIST')
  body=json.loads(request['input']);module=body['module'];sources=self.catalog.plan(module,strict_legacy=False);ids={s['id'] for s in sources}
  values=deepcopy(request);body['source_preferences']=[{'id':s['id'],'title':s['title'],'url':s['url'],'provenance':'CONFIGURED_PRIORITY_NON_EXCLUSIVE'} for s in sources];values['input']=canonical(body)
  for identity in acquisitions:
   with self.store.tx() as db:job,h,c=self.cache._row(db,identity,'WEB_CHECK_V1')
   if job.get('origin')=='COMPLEMENTARY':
    source=job['source'];require(digest(self.catalog.read()['value'])==job['catalog_sha256'] and module in source['modules'],'WEB_SOURCE_POLICY_CHANGED')
   else:source=self.catalog.source(job['source']['id']);require(source['id'] in ids and source['enabled'] and source_policy(source)==job['policy'],'WEB_SOURCE_POLICY_CHANGED')
   require(job.get('protocol_sha256')==self.protocol(),'WEB_EXTRACTION_VERSION_CHANGED')
   require(job['state']=='COMPLETE' and job['result']['cd_eligible'],'WEB_DOCUMENT_NOT_ADMISSIBLE')
   require(re.fullmatch('[a-f0-9]{32}',job['snapshot']),'WEB_SNAPSHOT_INVALID')
   folder=self.snapshot_folder(job['snapshot']);require(bytes_sha(folder/'acquisition.json')==job['evidence_sha256'] and bytes_sha(folder/'manifest.json')==job['manifest_sha256'],'WEB_EVIDENCE_CHANGED')
   evidence=json.loads((folder/'acquisition.json').read_text('utf8'));require(evidence['parser_sha256']==bytes_sha(Path(__file__)) and evidence['transport_sha256']==bytes_sha(Path(__file__).with_name('public_acquisition.py')),'WEB_EXTRACTION_VERSION_CHANGED')
   ref={'id':identity,'sha256':h,'source_id':source['id'],'module':module,'policy_sha256':job['policy'],'origin':job['origin']}
   self.cache.ingest_snapshot(values,folder,web_acquisition=ref)
  plan=self.cache.resolve(values,allow_cr=False);return self.cache.enrich(values,plan),plan

def complement_decision(results,coverage=None):
 """Pas d'inférence clinique à partir d'un HTTP 200, d'un mot-clé ou de la longueur."""
 from .sol_documentary_contracts import RecognizedCoverage
 require(coverage is None or type(coverage) is RecognizedCoverage,'SOL_COVERAGE_ATTESTATION_REQUIRED')
 if not results:return {'state':'NO_RESULTS','expand':False}
 if not any(r['status']=='ACCESSIBLE' and r.get('text_extracted') for r in results) and any(r['status'] in ('AUTHENTIFICATION_NECESSAIRE','ACCES_RESTREINT','ERREUR') for r in results):return {'state':'ACCESS_FAILURE_NOT_MEDICAL_INSUFFICIENCY','expand':False}
 if not any(r.get('text_extracted') for r in results):return {'state':'NO_CONTENT','expand':False}
 if not coverage:return {'state':'COVERAGE_UNDETERMINED','expand':False}
 decision=coverage.decision
 return {'state':decision['status'],'expand':decision['status']=='INSUFFICIENT','reason':decision['missing_requirements'],'packet_sha256':decision['packet_sha256']}

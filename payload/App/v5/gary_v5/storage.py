"""SQLite V5 uniquement. Transactions, intégrité et rejets persistants."""
import copy,hashlib,json,sqlite3,time
from contextlib import contextmanager
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA_ROOT=ROOT.parent.parent/'Data'
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()

class Store:
 def __init__(self,directory=None):
  self.root=Path(directory or DATA_ROOT).resolve()
  # Aucune destination extérieure, aucun partage de base V4.
  if self.root!=DATA_ROOT.resolve() and not self.root.is_relative_to(ROOT):raise ValueError('V5_STORAGE_REQUIRED')
  for p in (self.root,*self.root.parents):
   if p.is_symlink() or p.is_junction():raise ValueError('REPARSE_POINT_FORBIDDEN')
  self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'prototype.v1.sqlite'
  if self.path.is_symlink():raise ValueError('REPARSE_POINT_FORBIDDEN')
  with self.tx() as db:
   db.executescript('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS entries(id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,sha TEXT NOT NULL,created REAL NOT NULL); CREATE TABLE IF NOT EXISTS rejected(fingerprint TEXT PRIMARY KEY,reason TEXT,time REAL NOT NULL); CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY,event TEXT NOT NULL,reference TEXT NOT NULL,time REAL NOT NULL);')
   version=db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()
   if version and version[0]!='gary_v5_store_v1':raise ValueError('STORE_VERSION')
   db.execute("INSERT OR IGNORE INTO metadata VALUES('version','gary_v5_store_v1')")
   initial=json.loads((ROOT/'config/preferences.initial.json').read_text(encoding='utf8'))
   db.execute("INSERT OR IGNORE INTO metadata VALUES('preferences',?)",(canonical({'payload':initial,'sha':digest(initial)}),))
 @contextmanager
 def tx(self):
  db=sqlite3.connect(self.path,timeout=3,isolation_level=None)
  try:
   db.execute('BEGIN IMMEDIATE');yield db;db.commit()
  except BaseException:db.rollback();raise
  finally:db.close()
 def preferences(self,value=None,revision=None):
  with self.tx() as db:
   e=json.loads(db.execute("SELECT value FROM metadata WHERE key='preferences'").fetchone()[0]);old=e['payload']
   if e['sha']!=digest(old):raise ValueError('PREFERENCES_CORRUPT')
   validate_preferences(old)
   if value is None:return old
   if type(revision)is not int or revision!=old['revision']:raise ValueError('REVISION_CONFLICT')
   validate_preferences(value);value=copy.deepcopy(value);value['revision']=old['revision']+1
   db.execute("UPDATE metadata SET value=? WHERE key='preferences'",(canonical({'payload':value,'sha':digest(value)}),));return value
 def sources(self,value=None,revision=None):
  import re
  from urllib.parse import urlsplit
  initial=json.loads((ROOT/'config/source_priorities.initial.json').read_text(encoding='utf8'))
  with self.tx() as db:
   row=db.execute("SELECT value FROM metadata WHERE key='sources'").fetchone()
   if row:
    e=json.loads(row[0]);old=e['payload']
    if e['sha']!=digest(old):raise ValueError('SOURCE_SETTINGS_CORRUPT')
   else:old={**initial,'revision':0}
   if value is None:return old
   if type(revision)is not int or revision!=old['revision']:raise ValueError('REVISION_CONFLICT')
   if set(value)!=set(old) or value['schema']!=old['schema'] or set(value['modules'])!=set(old['modules']) or value['policy']!=initial['policy']:raise ValueError('SOURCES_INVALID')
   for m,group in value['modules'].items():
    if set(group)!={'sources','notes'} or group['notes']!=initial['modules'][m]['notes'] or not isinstance(group['sources'],list) or len(group['sources'])>100:raise ValueError('SOURCES_INVALID')
    defaults={r['id']:r for r in initial['modules'][m]['sources']};seen=set()
    for r in group['sources']:
     if set(r)!={'id','title','url','provenance'} or not isinstance(r['id'],str) or not re.fullmatch('[a-zA-Z0-9_-]{1,100}',r['id']) or r['id'] in seen:raise ValueError('SOURCE_DUPLICATE_OR_INVALID')
     seen.add(r['id'])
     if r['id'] in defaults:
      if r!=defaults[r['id']]:raise ValueError('INITIAL_REFERENCE_CHANGED')
     else:
      if not isinstance(r['title'],str) or not r['title'].strip() or len(r['title'])>200 or r['provenance']!='USER_V5':raise ValueError('SOURCE_TITLE_INVALID')
      u=urlsplit(r['url'])
      if u.scheme not in ('https','http') or not u.hostname or u.username or u.password or u.query or u.fragment or re.search(r'[\s\\]',r['url']):raise ValueError('SOURCE_URL_INVALID')
    if not set(defaults).issubset(seen):raise ValueError('INITIAL_REFERENCE_REMOVED')
   value=copy.deepcopy(value);value['revision']=old['revision']+1
   db.execute("INSERT OR REPLACE INTO metadata VALUES('sources',?)",(canonical({'payload':value,'sha':digest(value)}),));return value
 def put(self,kind,data,now=None):
  if kind not in ('CD','CR') or data.get('fictional') is not True:raise ValueError('FICTION_ONLY')
  now=time.time() if now is None else now
  identity=kind+'_'+digest(data)
  with self.tx() as db:
   if kind=='CR' and db.execute('SELECT 1 FROM rejected WHERE fingerprint=?',(data['response_fingerprint'],)).fetchone():raise ValueError('HUMAN_REJECTED')
   db.execute('INSERT OR IGNORE INTO entries VALUES(?,?,?,?,?)',(identity,kind,canonical(data),digest(data),now))
  return identity
 def rows(self,kind):
  with self.tx() as db:rows=db.execute('SELECT id,payload,sha,created FROM entries WHERE kind=? ORDER BY created DESC,id',(kind,)).fetchall()
  result=[]
  for identity,raw,h,created in rows:
   data=json.loads(raw)
   if digest(data)!=h:raise ValueError('CACHE_CORRUPT')
   result.append({'id':identity,'data':data,'sha':h,'created':created})
  return result
 def rejected(self,fingerprint):
  with self.tx() as db:return bool(db.execute('SELECT 1 FROM rejected WHERE fingerprint=?',(fingerprint,)).fetchone())
 def reject(self,identity,reason=None):
  if reason not in (None,'ERREUR_MEDICALE','SOURCE_INCORRECTE','REPONSE_INCOMPLETE','AUTRE'):raise ValueError('REASON_INVALID')
  with self.tx() as db:
   row=db.execute("SELECT payload,sha FROM entries WHERE kind='CR' AND id=?",(identity,)).fetchone()
   if not row:raise ValueError('CR_ABSENT')
   data=json.loads(row[0])
   if digest(data)!=row[1]:raise ValueError('CACHE_CORRUPT')
   db.execute('INSERT OR IGNORE INTO rejected VALUES(?,?,?)',(data['response_fingerprint'],reason,time.time()))
   db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('HUMAN_REJECTED',identity,time.time()))
  return {'id':identity,'state':'HUMAN_REJECTED','response_preserved':True,'generation_started':False}
 def revoke(self,identity):
  with self.tx() as db:
   row=db.execute("SELECT payload,sha FROM entries WHERE id=? AND kind='CD'",(identity,)).fetchone()
   if not row:raise ValueError('CD_ABSENT')
   data=json.loads(row[0])
   if digest(data)!=row[1]:raise ValueError('CACHE_CORRUPT')
   data['validity']='REVOKED';db.execute('UPDATE entries SET payload=?,sha=? WHERE id=?',(canonical(data),digest(data),identity))
   db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('CD_REVOKED_INVALIDATES_CR',identity,time.time()))
  return {'id':identity,'state':'REVOKED'}

def validate_preferences(v):
 modules={'DIAG','PATH','TTT','SUIVI','PED','PREG','ADM','FICH'}
 if set(v)!={'schema','revision','modules','provider','pricing_hypotheses'} or v['schema']!='gary_v5_preferences_v1' or type(v['revision'])is not int or v['revision']<0 or set(v['modules'])!=modules:raise ValueError('PREFERENCES_INVALID')
 if v['provider'] not in ('openai','google','mistral'):raise ValueError('PROVIDER_INVALID')
 for row in v['modules'].values():
  if set(row)!={'CD','CR'}:raise ValueError('POLICY_INVALID')
  for x in row.values():
   if set(x)!={'enabled','ttl_days','priority'} or type(x['enabled'])is not bool or type(x['ttl_days'])is not int or not 1<=x['ttl_days']<=3650 or x['priority'] not in ('low','medium','high','very_high'):raise ValueError('POLICY_INVALID')
 if set(v['pricing_hypotheses'])!={'openai','google','mistral'}:raise ValueError('PRICING_INVALID')
 for p in v['pricing_hypotheses'].values():
  if set(p)!={'input_per_million_usd','output_per_million_usd','search_usd'}:raise ValueError('PRICING_INVALID')
  for n in p.values():
   if n is not None and (type(n)not in (int,float) or not 0<=n<=10000):raise ValueError('PRICING_INVALID')

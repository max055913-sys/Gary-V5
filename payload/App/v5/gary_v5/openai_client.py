"""Client réseau historique, verrouillé. Aucun branchement au parcours OFFLINE."""
import json,sqlite3,ssl,urllib.request,urllib.error
from .storage import ROOT,digest
from .windows_vault import Vault,protect
from .generation_contract import (DEPTH_INSTRUCTIONS,CONTEXT_INSTRUCTIONS,DOCUMENTARY_INSTRUCTIONS,selected_conditions,load_system_prompt,build_request,validate_response,display_result)

TRANSPORT_ENABLED=False # Inchangé : aucune autorisation d’émission réelle.

def send(request,authorization=None):
 if not isinstance(authorization,dict) or set(authorization)!={'attempt_id','request_sha256'} or authorization['request_sha256']!=digest(request):raise PermissionError('NEW_EXPLICIT_API_AUTHORIZATION_REQUIRED')
 if not TRANSPORT_ENABLED:raise PermissionError('TRANSPORT_DISABLED_PENDING_NEW_COMMERCIAL_AUTHORIZATION')
 path=ROOT/'data/campaigns/V5-LIVE-01.sqlite'
 # Aucune réservation ni nouvelle autorisation n'est créée par le client.
 # Le seul registre existant est consommé : cette garde refuse toute émission.
 with sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True,isolation_level=None) as db:
  db.execute('BEGIN IMMEDIATE')
  row=db.execute('SELECT state,request_sha FROM attempts WHERE id=?',(authorization['attempt_id'],)).fetchone()
  token=db.execute('SELECT consumed,http_emissions,expires FROM single_authorization').fetchone()
  import time
  stopped=db.execute("SELECT value FROM campaign WHERE key='stopped'").fetchone()
  if row!=('SENT',digest(request)) or not token or token[0]!=1 or token[1]!=0 or token[2]<=time.time() or stopped!=('false',):db.rollback();raise PermissionError('COMMERCIAL_AUTHORIZATION_CONSUMED_OR_ABSENT')
  db.execute('UPDATE single_authorization SET http_emissions=1');db.commit()
 raw=bytearray(protect(Vault(ROOT/'data/private').path.read_bytes(),decrypt=True))
 try:
  if not raw.startswith(b'sk-') or any(chr(c).isspace() for c in raw):raise ValueError('LOCAL_CREDENTIAL_INVALID')
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*args):return None
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect(),urllib.request.HTTPSHandler(context=ssl.create_default_context()))
  req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(request,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+raw.decode('ascii'),'Content-Type':'application/json'},method='POST')
  with opener.open(req,timeout=60) as response:
   body=response.read(2097153)
   if len(body)>2097152:raise ValueError('RESPONSE_TOO_LARGE')
   return validate_response(json.loads(body))
 except Exception:raise RuntimeError('OPENAI_REQUEST_FAILED_NO_RETRY') from None
 finally:
  for i in range(len(raw)):raw[i]=0

"""Serveur local V5 autonome, port 8785, aucun appel automatique."""
import argparse,json,mimetypes,time,secrets,hmac,threading,socket
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from .gary_v5.application import Runtime
from .gary_v5.storage import Store,ROOT,DATA_ROOT
from .gary_v5.settings import Settings

def make_server(port=8785,directory=None,managed=None,generation_factory=None,workspace_factory=None,restart_launcher=None):
 store=Store(directory);runtime=Runtime(store)
 from .gary_v5.update_schedule import UpdateSchedule
 version=json.loads((ROOT/'release-version.json').read_text(encoding='utf8'))['version']
 from .gary_v5.update_releases import APPROVED_REPOSITORY,TRUSTED_PUBLIC_KEY,ReleaseDiscovery
 discovery=None
 if APPROVED_REPOSITORY and TRUSTED_PUBLIC_KEY and managed and store.root==DATA_ROOT.resolve():
  import platform,sys
  discovery=ReleaseDiscovery(APPROVED_REPOSITORY,TRUSTED_PUBLIC_KEY,version,sys.getwindowsversion().build,platform.machine().lower())
 updates=UpdateSchedule(store.root/'update-preferences.json',version,discovery)
 from .gary_v5.sol_web_gateway import SolWebGateway
 generation=generation_factory(runtime) if generation_factory else SolWebGateway(runtime,direct=store.root==DATA_ROOT.resolve())
 api_control=generation.transport if getattr(generation,'direct',False) else None
 lifecycle=threading.Condition()
 active_generations=0
 restarting=False
 stopping=False
 from .gary_v5.workspace_api import WorkspaceAPI
 if workspace_factory is not None:
  from .gary_v5.live_supervisor import TEST_ROOT
  if not store.root.is_relative_to(TEST_ROOT.resolve()):raise ValueError('WORKSPACE_FIXTURE_TEST_ONLY')
 workspace=(workspace_factory or WorkspaceAPI)(store)
 def autostart(enabled=None):
  if not managed or store.root!=DATA_ROOT.resolve():raise ValueError('AUTOSTART_MANAGED_SERVER_REQUIRED')
  from .gary_v5.windows_autostart import scheduled_start
  return scheduled_start(enabled)
 session_token=secrets.token_urlsafe(32)
 from .gary_v5.windows_vault import Vault
 vault=Vault(store.root/'private')
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass # aucun contenu de question ni secret journalisé
  def send(self,code,value,kind='application/json'):
   data=json.dumps(value,ensure_ascii=False).encode() if kind=='application/json' else value
   self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; img-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-src blob:; frame-ancestors 'none'");self.end_headers();self.wfile.write(data)
  def allowed(self):
   host=self.headers.get('Host','');origin=self.headers.get('Origin')
   return host==f'127.0.0.1:{self.server.server_port}' and origin in (None,'http://'+host)
  def reject_post(self,reason):
   # Vider un petit corps sans le décoder évite que Windows masque le 403
   # par un reset. Le délai couvre l’ensemble de la lecture.
   self.close_connection=True
   lengths=self.headers.get_all('Content-Length',[])
   if len(lengths)==1 and 'Transfer-Encoding' not in self.headers:
    try:
     remaining=int(lengths[0])
     if 0<remaining<=65536:
      deadline=time.monotonic()+2
      while remaining:
       timeout=deadline-time.monotonic()
       if timeout<=0:break
       self.connection.settimeout(timeout)
       chunk=self.rfile.read1(min(remaining,8192))
       if not chunk:break
       remaining-=len(chunk)
    except (ValueError,OSError):pass
   self.connection.settimeout(2)
   return self.send(403,{'error':reason})
  def do_GET(self):
   if not self.allowed():return self.send(403,{'error':'ORIGIN_REFUSED'})
   try:
    if self.path.startswith('/api/local/'):
     if not hmac.compare_digest(self.headers.get('X-Gary-Session',''),session_token):return self.send(403,{'error':'LOCAL_AUTHORIZATION_REFUSED'})
     if self.path.split('?',1)[0] in ('/api/local/source-account','/api/local/professional-browser'):return self.send(410,{'error':'PROFESSIONAL_ACCESS_ARCHIVED'})
     parts=self.path.split('/')
     if len(parts)==7 and parts[3]=='patient-export':return self.send(200,workspace.patient_file(parts[4],parts[5],parts[6]),mimetypes.guess_type(parts[6])[0] or 'application/octet-stream')
     if len(parts)==7 and parts[3]=='history-artifact':return self.send(200,workspace.history_file(parts[4],parts[5],parts[6]),mimetypes.guess_type(parts[6])[0] or 'application/octet-stream')
     if self.path=='/api/local/windows-autostart':
      try:return self.send(200,autostart())
      except ValueError as error:return self.send(503,{'error':str(error)})
     if self.path=='/api/local/updates':return self.send(200,updates.status())
     return self.send(200,workspace.get(self.path))
    if self.path.startswith('/api/generation/'):
     if not hmac.compare_digest(self.headers.get('X-Gary-Session',''),session_token):return self.send(403,{'error':'LOCAL_AUTHORIZATION_REFUSED'})
     parts=self.path.split('/')
     if len(parts)==5 and parts[3]=='status':return self.send(200,generation.status(parts[4]))
     if len(parts)==6 and parts[3]=='artifact':return self.send(200,generation.artifact(parts[4],parts[5]),mimetypes.guess_type(parts[5])[0] or 'application/octet-stream')
     return self.send(404,{'error':'NOT_FOUND'})
    if self.path=='/api/health':
     enabled=bool(api_control and api_control.enabled())
     configured=vault.status()['configured']
     return self.send(200,{'version':'V5','rag':False,'transport':enabled and configured,
                          'api':{'enabled':enabled,'key_configured':configured,'provider_verified':False}})
    if self.path=='/api/windows/identity':return self.send(200,{k:managed[k] for k in ('app','instance','pid','process_stamp','root_sha256','console_attached')} if managed else {'managed':False})
    if self.path=='/api/windows/session':return self.send(200,{'token':session_token,'managed':bool(managed),'active':True,'restart_supported':restart_launcher is not None,'instance':managed['instance'] if managed else None})
    if self.path=='/api/openai/key/status':return self.send(200,{**vault.status(),'api_enabled':bool(api_control and api_control.enabled())})
    if self.path=='/api/preferences':return self.send(200,store.preferences())
    if self.path=='/api/sources':return self.send(200,store.sources())
    if self.path=='/api/documentary/settings':return self.send(200,Settings(store).read_write(include_legacy_assignments=True))
    target=(ROOT/'dist'/('index.html' if self.path=='/' else self.path.lstrip('/'))).resolve()
    if not target.is_relative_to((ROOT/'dist').resolve()) or not target.is_file():return self.send(404,{'error':'NOT_FOUND'})
    self.send(200,target.read_bytes(),mimetypes.guess_type(target)[0] or 'application/octet-stream')
   except Exception:self.send(503,{'error':'LOCAL_READ_REFUSED'})
  def do_POST(self):
   nonlocal restarting,stopping,active_generations
   if not self.allowed():return self.reject_post('ORIGIN_REFUSED')
   start=time.perf_counter()
   try:
    sensitive=self.path in ('/api/openai/key','/api/openai/enabled','/api/windows/shutdown','/api/windows/restart','/api/windows/control') or self.path.startswith(('/api/generation/','/api/local/'))
    if sensitive:
     origin='http://127.0.0.1:'+str(self.server.server_port)
     expected=managed['control_token'] if self.path=='/api/windows/control' and managed else session_token
     provided=self.headers.get('X-Gary-Control' if self.path=='/api/windows/control' else 'X-Gary-Session','')
     if self.headers.get('Origin')!=origin or not hmac.compare_digest(provided,expected) or self.headers.get('Content-Type','').split(';')[0]!='application/json' or self.headers.get('Sec-Fetch-Site') not in (None,'same-origin'):
      return self.reject_post('LOCAL_AUTHORIZATION_REFUSED')
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<=(2200000 if self.path in ('/api/generation/capture','/api/local/draft/pdf') else 500000 if self.path.startswith('/api/local/') else 4096 if sensitive else 65536):raise ValueError('REQUEST_SIZE_INVALID')
    self.connection.settimeout(5)
    data=json.loads(self.rfile.read(n))
    if self.path=='/api/local/windows-autostart':
     if type(data) is not dict or set(data)!={'enabled'} or type(data['enabled']) is not bool:raise ValueError('AUTOSTART_INVALID')
     result=autostart(data['enabled'])
    elif self.path=='/api/local/updates/preferences':result=updates.preferences(data)
    elif self.path=='/api/local/updates/check':
     if data!={}:raise ValueError('UPDATE_CHECK_INVALID')
     updates.check(manual=True);result=updates.status()
    elif self.path=='/api/local/updates/download':
     if set(data)!={'version','confirmed'} or data['confirmed'] is not True:raise ValueError('UPDATE_CONFIRMATION_REQUIRED')
     updates.download(data['version']);result=updates.status()
    elif self.path=='/api/local/updates/install':
     if set(data)!={'version','confirmed'} or data['confirmed'] is not True:raise ValueError('UPDATE_CONFIRMATION_REQUIRED')
     import os,subprocess
     installation=ROOT.parent.parent.resolve()
     if (not managed or store.root!=DATA_ROOT.resolve() or
         installation!=(Path(os.environ['LOCALAPPDATA'])/'Gary').resolve() or
         (installation/'Gary.installation').read_bytes()!=b'Gary.Windows.PerUser.v1\n'):
      raise ValueError('UPDATE_INSTALLATION_REQUIRED')
     maintenance=installation/'MaintenanceRuntime'
     def launch(name):
      return subprocess.Popen([str(maintenance/'pythonw.exe'),'-B',str(maintenance/'GaryUpdate.pyw'),name],
                              cwd=maintenance,creationflags=subprocess.CREATE_NO_WINDOW)
     with lifecycle:
      if active_generations or restarting or stopping:raise ValueError('GENERATION_IN_PROGRESS')
      updates.install(data['version'],launch)
     result=updates.status()
    elif self.path.startswith('/api/local/'):result=workspace.post(self.path,data)
    elif self.path=='/api/openai/enabled':
     if api_control is None or set(data)!={'enabled'}:raise ValueError('API_SWITCH_INVALID')
     result=api_control.set_enabled(data['enabled'])
    elif self.path=='/api/openai/key':
     if data=={'action':'delete'}:result=vault.delete()
     elif isinstance(data,dict) and set(data)=={'action','key'} and data['action']=='save':result=vault.save(data['key'])
     else:raise ValueError('CREDENTIAL_REQUEST_INVALID')
    elif self.path in ('/api/windows/shutdown','/api/windows/control'):
     if not managed or data!={'action':'stop'}:raise ValueError('MANAGED_SERVER_REQUIRED')
     with lifecycle:
      if restarting:return self.send(409,{'error':'RESTART_IN_PROGRESS'})
      if not stopping:
       stopping=True
       threading.Thread(target=self.server.shutdown_after_generations,daemon=True).start()
      state='STOP_DEFERRED' if active_generations else 'STOPPING'
     return self.send(200,{'result':{'state':state,'live_enabled':False}})
    elif self.path=='/api/windows/restart':
     if not managed or restart_launcher is None or data!={'action':'restart'}:raise ValueError('MANAGED_SERVER_REQUIRED')
     with lifecycle:
      if active_generations:return self.send(409,{'error':'GENERATION_IN_PROGRESS'})
      if stopping:return self.send(409,{'error':'STOP_IN_PROGRESS'})
      if restarting:return self.send(409,{'error':'RESTART_IN_PROGRESS'})
      restart_launcher()
      restarting=True
     threading.Thread(target=lambda:(time.sleep(.2),self.server.shutdown()),daemon=True).start()
     return self.send(200,{'result':{'state':'RESTARTING','instance':managed['instance']}})
    elif self.path in ('/api/generation/prepare','/api/generation/confirm'):
     with lifecycle:
      if restarting:return self.send(409,{'error':'RESTART_IN_PROGRESS'})
      if stopping:return self.send(409,{'error':'STOP_IN_PROGRESS'})
      active_generations+=1
     try:
      result=(generation.prepare if self.path.endswith('/prepare') else generation.confirm)(data)
      return self.send(200,{'result':result,'server_seconds':time.perf_counter()-start})
     finally:
      with lifecycle:
       active_generations-=1
       lifecycle.notify_all()
    elif self.path=='/api/generation/metrics':result=generation.client_metrics(data)
    elif self.path=='/api/generation/capture':result=generation.capture(data)
    elif self.path=='/api/prepare':result=runtime.prepare(data)
    elif self.path=='/api/documentary/settings':result=Settings(store).read_write(data['value'],data['revision'],include_legacy_assignments=True)
    elif self.path=='/api/preferences':result=store.preferences(data['value'],data['revision'])
    elif self.path=='/api/sources':result=store.sources(data['value'],data['revision'])
    elif self.path=='/api/cr/reject':result=store.reject(data['id'],data.get('reason'))
    else:return self.send(404,{'error':'NOT_FOUND'})
    self.send(200,{'result':result,'server_seconds':time.perf_counter()-start})
   except (ValueError,KeyError,TypeError) as e:self.send(409 if str(e)=='REVISION_CONFLICT' else 422,{'error':'LOCAL_CREDENTIAL_OPERATION_REFUSED' if self.path=='/api/openai/key' else str(e) if isinstance(e,ValueError) else 'REQUEST_INVALID'})
   except Exception:self.send(503,{'error':'LOCAL_OPERATION_REFUSED'})
 class LocalServer(ThreadingHTTPServer):
  def drain_generations(self):
   nonlocal stopping
   with lifecycle:
    stopping=True
    lifecycle.wait_for(lambda:active_generations==0)
  def shutdown_after_generations(self):
   self.drain_generations()
   time.sleep(.2)
   self.shutdown()
  def server_bind(self):
   self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,0)
   if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
   # TCPServer.server_bind réappliquerait allow_reuse_address ; désactivé ici.
   self.allow_reuse_address=False;super().server_bind()
  def server_close(self):
   updates.stop.set()
   super().server_close()
 server=LocalServer(('127.0.0.1',port),Handler)
 threading.Thread(target=updates.run,daemon=True).start()
 return server

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8785);parser.add_argument('--data');a=parser.parse_args()
 server=make_server(a.port,a.data)
 print(f'Gary V5 — Prototype sans RAG : http://127.0.0.1:{server.server_port}',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:
  server.drain_generations()
  server.server_close()

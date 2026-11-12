"""Démarrage Windows à la demande ; identité vérifiée, jamais de kill par port."""
import ctypes,json,os,secrets,socket,subprocess,sys,time,urllib.request,urllib.error,uuid
from pathlib import Path
from contextlib import contextmanager
from .storage import ROOT,DATA_ROOT,digest
from .windows_vault import protect,atomic_bytes,safe_directory

DEFAULT_RUNTIME=DATA_ROOT/'windows_runtime';APP='gary_v5_windows_v1'
_children={}
class LocalError(RuntimeError):pass

def log(directory,code):
 # Liste fermée de codes : aucune exception brute, question, clé ou en-tête.
 allowed={'STARTED','REUSED','STOP_REQUESTED','STOPPED','PORT_CONFLICT','START_REFUSED','HOST_FAILED','RESTART_FAILED'}
 if code not in allowed:return
 p=safe_directory(directory)/'technical.log'
 lines=p.read_text(encoding='utf8').splitlines()[-79:] if p.exists() else []
 atomic_bytes(p,('\n'.join(lines+[time.strftime('%Y-%m-%d %H:%M:%S')+' '+code])+'\n').encode())

@contextmanager
def lock(directory,name,timeout=15):
 import msvcrt
 p=safe_directory(directory)/name
 if p.is_symlink():raise LocalError('RUNTIME_PATH_REFUSED')
 f=p.open('a+b');f.seek(0,2)
 if f.tell()==0:f.write(b'0');f.flush()
 deadline=time.monotonic()+timeout;held=False
 try:
  while True:
   try:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);held=True;break
   except OSError:
    if time.monotonic()>=deadline:raise LocalError('LAUNCH_ALREADY_IN_PROGRESS')
    time.sleep(.05)
  yield
 finally:
  if held:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
  f.close()

def process_identity(pid):
 from ctypes import wintypes
 kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
 kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)];kernel.GetProcessTimes.restype=wintypes.BOOL
 handle=kernel.OpenProcess(0x1000,False,pid)
 if not handle:return ('MISSING' if ctypes.get_last_error()==87 else 'UNKNOWN',None)
 try:
  fields=[wintypes.FILETIME() for _ in range(4)]
  if not kernel.GetProcessTimes(handle,*[ctypes.byref(f) for f in fields]):return 'UNKNOWN',None
  return 'FOUND',(fields[0].dwHighDateTime<<32)|fields[0].dwLowDateTime
 finally:kernel.CloseHandle(handle)

def process_stamp(pid):return process_identity(pid)[1]

def process_owner_state(owner):
 if not isinstance(owner,dict):return 'UNKNOWN'
 pid,stamp=owner.get('pid'),owner.get('stamp')
 if type(pid) is not int or not 0<pid<2**32 or type(stamp) is not int or stamp<=0:return 'UNKNOWN'
 state,current=process_identity(pid)
 if state=='MISSING' or state=='FOUND' and current!=stamp:return 'GONE'
 return 'ACTIVE' if state=='FOUND' else 'UNKNOWN'

def record(directory):
 p=Path(directory)/'owner.dpapi'
 if not p.exists():return None
 if p.is_symlink():raise LocalError('RUNTIME_PATH_REFUSED')
 try:
  r=json.loads(protect(p.read_bytes(),decrypt=True))
  if r['app']!=APP or r['root_sha256']!=digest(str(ROOT.resolve())):raise ValueError()
  return r
 except Exception:raise LocalError('SERVER_IDENTITY_UNREADABLE') from None

def local_call(port,path,body=None,token=None,timeout=2):
 base=f'http://127.0.0.1:{port}';headers={'Content-Type':'application/json','Origin':base}
 if token:headers['X-Gary-Control']=token
 request=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
 # Aucune configuration proxy héritée pour le contrôle local.
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 with opener.open(request,timeout=timeout) as response:return json.load(response)

def identity_matches(r,port):
 if not r or r.get('port')!=port or process_stamp(r['pid'])!=r['process_stamp']:return False
 try:
  value=local_call(port,'/api/windows/identity')
  return value=={k:r[k] for k in ('app','instance','pid','process_stamp','root_sha256','console_attached')}
 except Exception:return False

def occupied(port):
 with socket.socket() as s:s.settimeout(.3);return s.connect_ex(('127.0.0.1',port))==0

def chrome_path():
 import winreg
 for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
  try:
   with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') as key:p=Path(winreg.QueryValue(key,None))
   if p.is_file():return p
  except OSError:pass
 for var,suffix in (('PROGRAMFILES','Google/Chrome/Application/chrome.exe'),('PROGRAMFILES(X86)','Google/Chrome/Application/chrome.exe'),('LOCALAPPDATA','Google/Chrome/Application/chrome.exe')):
  p=Path(os.environ.get(var,''))/suffix
  if p.is_file():return p
 raise LocalError('CHROME_NOT_FOUND')

def open_chrome(port):os.startfile(f'http://127.0.0.1:{port}')

def start(directory=DEFAULT_RUNTIME,data=None,port=8785,browser=True):
 directory=Path(directory)
 with lock(directory,'launch.lock'):
  if (DATA_ROOT.parent/'maintenance.active').exists():raise LocalError('MAINTENANCE_IN_PROGRESS')
  r=record(directory)
  if identity_matches(r,port):log(directory,'REUSED');result={'state':'REUSED','pid':r['pid'],'instance':r['instance']}
  else:
   if occupied(port):log(directory,'PORT_CONFLICT');raise LocalError('PORT_OCCUPIED_BY_UNVERIFIED_SERVICE')
   if r and process_stamp(r['pid'])==r['process_stamp']:raise LocalError('IDENTIFIED_SERVER_NOT_RESPONDING')
   pythonw=ROOT/'runtime/python/pythonw.exe'
   if not pythonw.is_file():raise LocalError('V5_PYTHONW_MISSING')
   args=[str(pythonw),str(ROOT/'windows_host.pyw'),'--runtime',str(directory),'--data',str(data or DATA_ROOT),'--port',str(port)]
   child=subprocess.Popen(args,cwd=ROOT.parent,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
   deadline=time.monotonic()+20
   while time.monotonic()<deadline:
    r=record(directory)
    if identity_matches(r,port):break
    if child.poll() is not None:raise LocalError('GARY_START_FAILED')
    time.sleep(.1)
   else:raise LocalError('GARY_START_TIMEOUT_NO_PROCESS_KILLED')
   result={'state':'STARTED','pid':r['pid'],'instance':r['instance']}
   _children[r['instance']]=child
  if browser:open_chrome(port)
  return result

def stop(directory=DEFAULT_RUNTIME,port=8785):
 with lock(directory,'launch.lock'):
  r=record(directory)
  if not r:return {'state':'ALREADY_STOPPED'}
  if not identity_matches(r,port):
   if process_stamp(r['pid'])!=r['process_stamp'] and not occupied(port):return {'state':'STALE_RECORD_NO_PROCESS_STOPPED'}
   raise LocalError('UNVERIFIED_SERVICE_NOT_STOPPED')
  result=local_call(port,'/api/windows/control',{'action':'stop'},r['control_token']);log(directory,'STOP_REQUESTED')
  if result['result']['state']=='STOP_DEFERRED':return {'state':'STOP_DEFERRED'}
  deadline=time.monotonic()+10
  while time.monotonic()<deadline:
   if not identity_matches(r,port):
    child=_children.pop(r['instance'],None)
    if child:
     try:child.wait(timeout=3)
     except subprocess.TimeoutExpired:_children[r['instance']]=child
    return {'state':'STOPPED'}
   time.sleep(.1)
  raise LocalError('STOP_PENDING_NO_FORCE_KILL')

def launch_restart(directory,data,port,owner):
 pythonw=ROOT/'runtime/python/pythonw.exe'
 args=[str(pythonw),str(ROOT/'windows_host.pyw'),'--runtime',str(directory),'--data',str(data),'--port',str(port),
       '--restart-pid',str(owner['pid']),'--restart-stamp',str(owner['process_stamp'])]
 subprocess.Popen(args,cwd=ROOT.parent,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                  stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)

def restart_after_exit(directory,data,port,pid,stamp):
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  if process_stamp(pid)!=stamp and not occupied(port):
   return start(directory,data,port,browser=False)
  time.sleep(.1)
 raise LocalError('RESTART_OLD_PROCESS_STILL_ACTIVE')

def host(directory,data,port):
 from v5.server import make_server
 directory=Path(directory)
 with lock(directory,'server.lock',timeout=.1):
  r={'app':APP,'instance':uuid.uuid4().hex,'pid':os.getpid(),'process_stamp':process_stamp(os.getpid()),'root_sha256':digest(str(ROOT.resolve())),'control_token':secrets.token_urlsafe(32),'port':port,'console_attached':bool(ctypes.windll.kernel32.GetConsoleWindow())}
  server=make_server(port,data,managed=r,restart_launcher=lambda:launch_restart(directory,data,port,r))
  atomic_bytes(directory/'owner.dpapi',protect(json.dumps(r).encode()));log(directory,'STARTED')
  try:server.serve_forever(poll_interval=.1)
  finally:
   server.drain_generations()
   server.server_close();current=record(directory)
   if current and current['instance']==r['instance']:(directory/'owner.dpapi').unlink(missing_ok=True)
   log(directory,'STOPPED')

def error_box(code):
 messages={'PORT_OCCUPIED_BY_UNVERIFIED_SERVICE':'Le port 8785 est utilisé par un autre service ou un ancien Gary non identifié. Aucun processus n’a été arrêté. Fermez-le manuellement puis réessayez.','CHROME_NOT_FOUND':'Google Chrome est introuvable. Gary reste local ; installez ou indiquez Chrome avant de relancer.','UNVERIFIED_SERVICE_NOT_STOPPED':'Le service n’a pas pu être identifié comme Gary V5. Aucun arrêt forcé n’a été effectué.'}
 ctypes.windll.user32.MessageBoxW(None,messages.get(code,'Gary ne peut pas terminer cette opération. Consultez le rapport d’installation et le journal technique local.'),'Gary',0x10)

def main():
 silent=sys.argv[1:]==['start-silent']
 try:
  if len(sys.argv)!=2 or sys.argv[1] not in ('start','start-silent','stop'):raise LocalError('ACTION_INVALID')
  result=start(browser=not silent) if sys.argv[1]!='stop' else stop()
  if result['state']=='STOP_DEFERRED':
   ctypes.windll.user32.MessageBoxW(None,'Gary s’arrêtera après l’opération en cours. Si elle reste bloquée, une fermeture forcée peut laisser un appel déjà émis facturable.','Gary',0x40)
  return result
 except Exception as e:
  log(DEFAULT_RUNTIME,'START_REFUSED')
  if silent:raise SystemExit(1) from None
  error_box(str(e) if isinstance(e,LocalError) else 'LOCAL_OPERATION_REFUSED');return None

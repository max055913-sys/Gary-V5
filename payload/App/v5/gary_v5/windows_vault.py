"""Protection DPAPI utilisateur. Aucun accès API et aucune route de restitution."""
import ctypes,os,re,uuid,time
from ctypes import wintypes
from pathlib import Path

class Blob(ctypes.Structure):_fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(raw,decrypt=False):
 if os.name!='nt':raise OSError('WINDOWS_REQUIRED')
 crypt=ctypes.WinDLL('crypt32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
 buf=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buf,ctypes.POINTER(ctypes.c_ubyte)));dest=Blob()
 function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
 function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)];function.restype=wintypes.BOOL
 kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
 try:
  if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(dest)):raise ValueError('DPAPI_OPERATION_REFUSED')
  return ctypes.string_at(dest.data,dest.size)
 finally:
  ctypes.memset(buf,0,len(raw))
  if dest.data:ctypes.memset(dest.data,0,dest.size);kernel.LocalFree(dest.data)

def safe_directory(path):
 path=Path(path).absolute()
 for p in (path,*path.parents):
  if p.is_symlink() or p.is_junction():raise ValueError('PRIVATE_PATH_REFUSED')
 path.mkdir(parents=True,exist_ok=True);return path

def atomic_bytes(path,raw):
 path=Path(path);safe_directory(path.parent)
 if path.is_symlink():raise ValueError('PRIVATE_PATH_REFUSED')
 tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
 with tmp.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
 for attempt in range(8):
  try:os.replace(tmp,path);break
  except PermissionError:
   if attempt==7:raise
   time.sleep(.05*(attempt+1))

class Vault:
 def __init__(self,directory):self.directory=Path(directory);self.path=self.directory/'openai.dpapi'
 def status(self):
  if self.path.is_symlink() or self.directory.is_symlink() or self.directory.is_junction():raise ValueError('PRIVATE_PATH_REFUSED')
  return {'configured':self.path.is_file(),'storage':'WINDOWS_DPAPI_CURRENT_USER','key_returned':False,'connection_tested':False,'live_enabled':False}
 def save(self,value):
  if not isinstance(value,str) or not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,500}',value):raise ValueError('API_KEY_FORMAT_REFUSED')
  atomic_bytes(self.path,protect(value.encode('utf8')));return self.status()
 def delete(self):
  safe_directory(self.directory)
  if self.path.is_symlink():raise ValueError('PRIVATE_PATH_REFUSED')
  self.path.unlink(missing_ok=True);return self.status()

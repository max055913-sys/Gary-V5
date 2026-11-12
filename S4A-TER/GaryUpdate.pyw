"""Independent Windows updater. Run with Python located outside the installation."""
import ctypes
import json
import msvcrt
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from maintenance_transaction import check_owner, recover, update

ROOT = Path(os.environ['LOCALAPPDATA'])/'Gary'
APP = ROOT/'App'
PYTHON = APP/'v5/runtime/python/python.exe'
GATE = ROOT/'maintenance.active'


def child(code, *args, timeout=60):
    result = subprocess.run([str(PYTHON),'-B','-c',code,*map(str,args)],cwd=APP,
                            capture_output=True,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise ValueError('UPDATE_LOCAL_CHECK_FAILED')
    return result.stdout


def authenticate(archive):
    proof = archive.with_suffix('.json')
    signature = archive.with_suffix('.sig')
    code = """
import json,platform,re,sys
from datetime import datetime,timezone
from pathlib import Path
from v5.gary_v5.storage import ROOT
from v5.gary_v5.update_releases import APPROVED_REPOSITORY,TRUSTED_PUBLIC_KEY,ReleaseDiscovery,strict_json,version_tuple,ASSET,LIMIT
if not APPROVED_REPOSITORY or not TRUSTED_PUBLIC_KEY:raise ValueError()
p,s=map(Path,sys.argv[1:])
with p.open('rb') as f:raw=f.read(65537)
with s.open('rb') as f:sig=f.read(65)
if len(raw)>65536 or len(sig)!=64:raise ValueError()
current=json.loads((ROOT/'release-version.json').read_text())['version']
client=ReleaseDiscovery(APPROVED_REPOSITORY,TRUSTED_PUBLIC_KEY,current,sys.getwindowsversion().build,platform.machine().lower())
client.verify(raw,sig)
m=strict_json(raw)
if not (m['schema']=='gary-update-v1' and m['product']=='Gary' and m['repository']==APPROVED_REPOSITORY
 and m['channel']=='stable' and '-' not in m['version'] and version_tuple(m['version'])>version_tuple(current)
 and m['architecture']==client.architecture and type(m['min_windows_build']) is int
 and m['min_windows_build']<=client.windows_build and datetime.fromisoformat(m['expires_at'])>datetime.now(timezone.utc)
 and m['asset']==ASSET and type(m['bytes']) is int and 0<m['bytes']<=LIMIT and re.fullmatch(r'[a-f0-9]{64}',m['sha256'])):raise ValueError()
print(json.dumps([m['version'],m['sha256'],m['data_schema'],m['bytes']]))
"""
    from maintenance_transaction import check_path
    for file in (archive,proof,signature):
        check_path(file)
    version,digest,schema,size = json.loads(child(code,proof,signature))
    if archive.stat().st_size != size:
        raise ValueError('UPDATE_SIZE_MISMATCH')
    return version,digest,schema


def stop_gary():
    child("""
import time
from v5.gary_v5.windows_app import stop,record,occupied,process_stamp,DEFAULT_RUNTIME
from v5.gary_v5.uninstall_prepare import wait_owned_processes
owner=record(DEFAULT_RUNTIME)
stop()
deadline=time.monotonic()+45
while occupied(8785) or owner and process_stamp(owner['pid'])==owner['process_stamp']:
    if time.monotonic()>=deadline:raise TimeoutError()
    time.sleep(.1)
wait_owned_processes()
""")


def stopped():
    import socket
    with socket.socket() as s:
        s.settimeout(.5)
        return s.connect_ex(('127.0.0.1',8785)) != 0


def probe(_app):
    child("""
import tempfile,threading,urllib.request
from v5.server import make_server
from v5.gary_v5.storage import ROOT
with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
    server=make_server(0,directory=tmp)
    worker=threading.Thread(target=server.serve_forever);worker.start()
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/',timeout=3) as reply:
            if reply.status!=200 or b'<title>Gary</title>' not in reply.read():raise ValueError()
    finally:
        server.shutdown();server.server_close();worker.join()
""",timeout=20)
    return True


def maintain():
    if (ROOT/'uninstall.pending').exists():
        raise ValueError('UNINSTALL_RECOVERY_REQUIRED')
    if Path(sys.executable).resolve().is_relative_to(APP.resolve()):
        raise ValueError('UPDATE_RUNTIME_MUST_BE_EXTERNAL')
    check_owner(ROOT)
    args = sys.argv[1:]
    if args == ['--recover']:
        if not GATE.is_file():
            raise ValueError('UPDATE_NO_INTERRUPTION')
        if GATE.read_bytes()==b'gary-uninstall-v1':
            raise ValueError('UNINSTALL_RECOVERY_REQUIRED')
        recover(ROOT,stopped)
        archive_work()
        GATE.unlink()
        ctypes.windll.user32.MessageBoxW(None,'Maintenance terminée. Vous pouvez rouvrir Gary.', 'Gary',0)
        return
    if len(args)!=1 or not re.fullmatch(r'[a-f0-9]{32}\.zip',args[0]):
        raise ValueError('UPDATE_PACKAGE_NAME_INVALID')
    archive = ROOT/'Updates'/args[0]
    if archive.resolve() != ROOT.resolve()/'Updates'/args[0]:
        raise ValueError('UPDATE_PACKAGE_PATH_INVALID')
    proof = authenticate(archive)
    if ctypes.windll.user32.MessageBoxW(None,f'Installer Gary {proof[0]} après arrêt contrôlé ?', 'Gary',0x21)!=1:
        return
    with GATE.open('xb'):
        pass
    try:
        stop_gary()
        update(ROOT,archive,lambda:authenticate(archive),True,stopped,probe)
    finally:
        work = ROOT/'Maintenance'
        if (ROOT/'App').is_dir() and (not (work/'previous-App').exists() or (work/'committed').exists()):
            GATE.unlink(missing_ok=True)
    archive_work()
    if ctypes.windll.user32.MessageBoxW(None,'Mise à jour vérifiée. Ouvrir Gary maintenant ?', 'Gary',0x24)==6:
        subprocess.Popen([sys.executable,str(ROOT/'Gary.pyw'),'start'],creationflags=subprocess.CREATE_NO_WINDOW)


def archive_work():
    work=ROOT/'Maintenance'
    if work.exists():
        work.rename(ROOT/('Maintenance-'+uuid.uuid4().hex))


def main():
    check_owner(ROOT)
    lock = ROOT/'maintenance.lock'
    if lock.exists():
        from maintenance_transaction import check_path
        check_path(lock)
    with lock.open('a+b') as stream:
        stream.seek(0)
        msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        try:
            maintain()
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)


if __name__=='__main__':
    try:
        main()
    except Exception:
        ctypes.windll.user32.MessageBoxW(None,'Mise à jour refusée ou interrompue. Consultez le rapport de maintenance.', 'Gary',0x10)
        sys.exit(1)

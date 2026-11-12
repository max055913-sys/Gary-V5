"""Tâche d’ouverture de session, toujours gérée au nom de l’utilisateur courant."""
import base64
import json
import os
from pathlib import Path
import subprocess
import threading

from .storage import ROOT, digest
from .commercial_supervisor import require

_lock = threading.Lock()

def scheduled_start(enabled=None):
    require(enabled is None or type(enabled) is bool,'AUTOSTART_INVALID')
    operation='status' if enabled is None else 'enable' if enabled else 'disable'
    return _task_operation(operation, enabled)

def remove_owned_task():
    result = _task_operation('remove', False)
    require(result['state']=='ABSENT','AUTOSTART_REMOVE_NOT_CONFIRMED')

def _task_operation(operation, enabled):
    task_name='Gary-Logon-'+digest([str(ROOT.resolve()).casefold(),str(Path.home()).casefold()])[:16]
    env={**os.environ,'GARY_AUTOSTART_TASK':task_name,'GARY_AUTOSTART_ROOT':str(ROOT.resolve()),'GARY_AUTOSTART_OPERATION':operation}
    script=Path(__file__).with_suffix('.ps1').read_text(encoding='utf-8-sig')
    encoded=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    try:
        with _lock:
            result=subprocess.run([str(powershell),'-NoLogo','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                                  env=env,capture_output=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode!=0:raise ValueError()
        state=json.loads(result.stdout)
        if state.get('state') not in ('ABSENT','ENABLED','DISABLED','MODIFIED') or type(state.get('enabled')) is not bool:raise ValueError()
    except (OSError,ValueError,AttributeError,subprocess.TimeoutExpired):
        raise ValueError('AUTOSTART_SCHEDULER_UNAVAILABLE') from None
    if enabled is not None:
        require(state['state']!='MODIFIED','AUTOSTART_TASK_MODIFIED')
        require(state['enabled'] is enabled,'AUTOSTART_CHANGE_NOT_CONFIRMED')
    return state

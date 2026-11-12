from pathlib import Path
import sys,argparse
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from v5.gary_v5.windows_app import host,log,restart_after_exit
p=argparse.ArgumentParser();p.add_argument('--runtime',required=True);p.add_argument('--data',required=True);p.add_argument('--port',required=True,type=int)
p.add_argument('--restart-pid',type=int);p.add_argument('--restart-stamp',type=int);a=p.parse_args()
if (a.restart_pid is None)!=(a.restart_stamp is None):p.error('Identité de redémarrage incomplète')
try:
 if a.restart_pid is None:host(a.runtime,a.data,a.port)
 else:restart_after_exit(a.runtime,a.data,a.port,a.restart_pid,a.restart_stamp)
except Exception:log(a.runtime,'HOST_FAILED' if a.restart_pid is None else 'RESTART_FAILED')

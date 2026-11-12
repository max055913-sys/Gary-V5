"""Stable entry for the installed and unpacked layout."""
from pathlib import Path
import runpy
import sys

installation = Path(__file__).resolve().parent
if (installation / 'uninstall.pending').exists():
    sys.exit()
if (installation / 'maintenance.active').exists():
    if (installation / 'maintenance.active').read_bytes() == b'gary-uninstall-v1':
        sys.exit()
    import os
    import subprocess
    if (sys.argv[1:] in ([], ['start'])
            and installation == (Path(os.environ['LOCALAPPDATA'])/'Gary').resolve()
            and (installation/'Gary.installation').is_file()):
        runtime = installation/'MaintenanceRuntime'
        subprocess.Popen([str(runtime/'pythonw.exe'), str(runtime/'GaryUpdate.pyw'), '--recover'],
                         creationflags=subprocess.CREATE_NO_WINDOW)
    sys.exit()
root = installation / 'App/v5'
sys.argv = [str(root / 'windows_launcher.pyw'), *(sys.argv[1:] or ['start'])]
runpy.run_path(sys.argv[0], run_name='__main__')

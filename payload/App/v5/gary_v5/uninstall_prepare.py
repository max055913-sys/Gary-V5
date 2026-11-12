"""Prepare an owned Windows installation for removal without terminating processes."""
import os
from pathlib import Path
import subprocess
import time

from .storage import DATA_ROOT, ROOT
from .windows_app import DEFAULT_RUNTIME, occupied, process_stamp, record, stop
from .windows_autostart import remove_owned_task


def wait_owned_processes():
    powershell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    script = ("$ErrorActionPreference='Stop'; $prefix=$env:GARY_MAINT_APP+'\\'; "
              "Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne [int]$env:GARY_MAINT_PID "
              "-and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($prefix,[StringComparison]::OrdinalIgnoreCase) } "
              "| Select-Object -ExpandProperty ProcessId")
    end = time.monotonic() + 12
    while True:
        result = subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-Command',script],
                                env={**os.environ,'GARY_MAINT_APP':str(ROOT.parent),'GARY_MAINT_PID':str(os.getpid())},
                                capture_output=True,check=True,timeout=4,creationflags=subprocess.CREATE_NO_WINDOW)
        if not result.stdout.strip():
            return
        if time.monotonic() >= end:
            raise TimeoutError('MAINTENANCE_CHILD_PROCESS_ACTIVE')
        time.sleep(.2)


def main():
    if not (DATA_ROOT.parent/'maintenance.active').is_file():
        raise ValueError('MAINTENANCE_NOT_HELD')
    owner = record(DEFAULT_RUNTIME)
    stop()
    end = time.monotonic() + 45
    while occupied(8785) or owner and process_stamp(owner['pid']) == owner['process_stamp']:
        if time.monotonic() >= end:
            raise TimeoutError('MAINTENANCE_ACTIVE')
        time.sleep(.1)
    wait_owned_processes()
    remove_owned_task()


if __name__ == '__main__':
    main()

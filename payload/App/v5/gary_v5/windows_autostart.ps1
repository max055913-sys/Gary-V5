$ErrorActionPreference = 'Stop'
$taskName = $env:GARY_AUTOSTART_TASK
$root = $env:GARY_AUTOSTART_ROOT
$operation = $env:GARY_AUTOSTART_OPERATION
$user = [Security.Principal.WindowsIdentity]::GetCurrent()
$sid = $user.User.Value
$exe = Join-Path $root 'runtime\python\pythonw.exe'
$launcher = Join-Path $root 'windows_launcher.pyw'
$arguments = '"' + $launcher + '" start-silent'
$description = 'Gary - ouverture de session, serveur local uniquement'

function UserSid($identity) {
    if (!$identity) { return '' }
    if ($identity -match '^S-1-') { return $identity }
    try { return ([Security.Principal.NTAccount]::new($identity)).Translate([Security.Principal.SecurityIdentifier]).Value }
    catch { return '' }
}

function ReadTask {
    Get-ScheduledTask -TaskPath '\' | Where-Object TaskName -eq $taskName
}

function IsExpected($task) {
    return (@($task.Actions).Count -eq 1 -and @($task.Triggers).Count -eq 1 -and
        $task.Description -ceq $description -and
        $task.Actions[0].Execute -eq $exe -and $task.Actions[0].Arguments -ceq $arguments -and
        $task.Actions[0].WorkingDirectory -eq (Split-Path $root) -and
        $task.Triggers[0].CimClass.CimClassName -eq 'MSFT_TaskLogonTrigger' -and
        (UserSid $task.Triggers[0].UserId) -eq $sid -and $task.Triggers[0].Enabled -and
        !$task.Triggers[0].Repetition.Interval -and
        (UserSid $task.Principal.UserId) -eq $sid -and
        $task.Principal.LogonType -eq 'Interactive' -and $task.Principal.RunLevel -eq 'Limited' -and
        $task.Settings.MultipleInstances -eq 'IgnoreNew' -and !$task.Settings.StartWhenAvailable -and
        !$task.Settings.WakeToRun -and !$task.Settings.RestartCount)
}

function Report($task) {
    if (!$task) { return @{state='ABSENT'; enabled=$false} }
    if (!(IsExpected $task)) { return @{state='MODIFIED'; enabled=[bool]$task.Settings.Enabled} }
    if ($task.Settings.Enabled) { return @{state='ENABLED'; enabled=$true} }
    return @{state='DISABLED'; enabled=$false}
}

$task = ReadTask
if ($operation -ne 'status') {
    if ($task -and !(IsExpected $task)) { @{state='MODIFIED'; enabled=[bool]$task.Settings.Enabled} | ConvertTo-Json -Compress; exit 0 }
    if ($operation -eq 'enable') {
        if (!(Test-Path -LiteralPath $exe -PathType Leaf) -or !(Test-Path -LiteralPath $launcher -PathType Leaf)) { throw 'LAUNCHER_MISSING' }
        if (!$task) {
            $action = New-ScheduledTaskAction -Execute $exe -Argument $arguments -WorkingDirectory (Split-Path $root)
            $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user.Name
            $principal = New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
            $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
            Register-ScheduledTask -TaskName $taskName -TaskPath '\' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description $description | Out-Null
        } elseif (!$task.Settings.Enabled) {
            $task | Enable-ScheduledTask | Out-Null
        }
    } elseif ($operation -eq 'disable') {
        if ($task -and $task.Settings.Enabled) { $task | Disable-ScheduledTask | Out-Null }
    } elseif ($operation -eq 'remove') {
        if ($task) { $task | Unregister-ScheduledTask -Confirm:$false }
    } else { throw 'INVALID_OPERATION' }
    $task = ReadTask
}
Report $task | ConvertTo-Json -Compress

param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$PythonZip,
    [Parameter(Mandatory=$true)][string]$NodeZip,
    [Parameter(Mandatory=$true)][string]$Output
)
$ErrorActionPreference='Stop'
$build=Split-Path $PSScriptRoot -Parent
$pythonExe=(Get-Command $Python -CommandType Application).Source
$compiler=Join-Path $env:WINDIR 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
if (!(Test-Path -LiteralPath $compiler -PathType Leaf)) {throw 'Compilateur .NET Framework x64 absent'}
$locked=Get-Content -Raw -LiteralPath (Join-Path $build 'runtimes.lock.json') | ConvertFrom-Json
$output=[IO.Path]::GetFullPath($Output)
& $pythonExe -B (Join-Path $build 'construire_s4a_bis.py') --output $output --python-zip $PythonZip --python-sha256 $locked.python.sha256 --node-zip $NodeZip --node-sha256 $locked.node.sha256
if($LASTEXITCODE){throw 'Construction ZIP en échec'}
$stage=New-Item -ItemType Directory -Path (Join-Path ([IO.Path]::GetTempPath()) ('gary-compiler-'+[guid]::NewGuid().ToString('N')))
Copy-Item -LiteralPath (Join-Path $build 'Installer.cs') -Destination $stage.FullName
Push-Location -LiteralPath $stage.FullName
try {
    $refs=@('/reference:System.Windows.Forms.dll','/reference:System.IO.Compression.dll','/reference:Microsoft.CSharp.dll')
    & $compiler /nologo /target:winexe /platform:x64 /define:UNINSTALLER @refs /out:Uninstall_Gary.exe Installer.cs
    if($LASTEXITCODE){throw 'Compilation du désinstallateur en échec'}
    $zip=Join-Path $output 'Gary_V5_Portable.zip'
    & $compiler /nologo /target:winexe /platform:x64 @refs "/resource:$zip,payload.zip" '/resource:Uninstall_Gary.exe,uninstaller.exe' /out:Installer_Gary.exe Installer.cs
    if($LASTEXITCODE){throw 'Compilation installateur en échec'}
    $installer=Join-Path $stage.FullName 'Installer_Gary.exe'
    $assembly=[Reflection.Assembly]::LoadFile($installer)
    foreach($pair in @(@{Resource='payload.zip'; File=$zip},@{Resource='uninstaller.exe'; File=(Join-Path $stage.FullName 'Uninstall_Gary.exe')})){
        $stream=$assembly.GetManifestResourceStream($pair.Resource)
        $sha=[Security.Cryptography.SHA256]::Create()
        try{$actual=[BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-','')}
        finally{$stream.Dispose();$sha.Dispose()}
        if($actual -ne (Get-FileHash -LiteralPath $pair.File).Hash){throw 'Ressource intégrée divergente'}
    }
    Copy-Item -LiteralPath $installer -Destination $output
    Get-FileHash -LiteralPath (Join-Path $output 'Installer_Gary.exe'),$zip |
        ForEach-Object {"$($_.Hash)  $(Split-Path $_.Path -Leaf)"} |
        Set-Content -LiteralPath (Join-Path $output 'SHA256SUMS.txt') -Encoding ascii
} finally {Pop-Location}


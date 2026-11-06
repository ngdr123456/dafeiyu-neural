param(
    [string]$OutputName = 'BirthChat-DeepSeek-Windows-20261106',
    [string]$PythonRoot = 'C:\Users\22082\.cache\codex-runtimes\codex-primary-runtime\dependencies\python'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if ($OutputName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') { throw 'OutputName must be a single directory name.' }
$out = Join-Path $repo ("dist\" + $OutputName)
if (Test-Path -LiteralPath $out) { throw 'Output already exists; choose a fresh build directory manually. Nothing overwritten.' }
if (!(Test-Path -LiteralPath (Join-Path $PythonRoot 'pythonw.exe'))) { throw 'CPython with Tk is required.' }
New-Item -ItemType Directory -Path (Join-Path $out 'runtime\Lib') -Force | Out-Null
# Exact source allowlist: no state, credentials, logs, tests, environment or cache.
New-Item -ItemType Directory -Path (Join-Path $out 'birth') | Out-Null
Get-ChildItem -LiteralPath (Join-Path $repo 'birth') -Filter '*.py' -File | Copy-Item -Destination (Join-Path $out 'birth')
foreach ($name in @('Start-BirthChat.cmd', 'start_birth_chat.pyw', 'accept_birth_chat.py', 'WINDOWS_CHAT.md')) {
    Copy-Item -LiteralPath (Join-Path $repo $name) -Destination $out
}
foreach ($name in @('python.exe','pythonw.exe','python3.dll','python312.dll','vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt')) {
    Copy-Item -LiteralPath (Join-Path $PythonRoot $name) -Destination (Join-Path $out 'runtime')
}
foreach ($name in @('DLLs', 'tcl')) {
    Copy-Item -LiteralPath (Join-Path $PythonRoot $name) -Destination (Join-Path $out 'runtime') -Recurse
}
Get-ChildItem -LiteralPath (Join-Path $PythonRoot 'Lib') | Where-Object {
    $_.Name -notin @('site-packages', '__pycache__', 'test', 'tests')
} | Copy-Item -Destination (Join-Path $out 'runtime\Lib') -Recurse
# -I isolates user site packages; this file keeps bundled Python paths explicit.
@('python312.zip', '.', 'Lib', 'DLLs') | Set-Content -LiteralPath (Join-Path $out 'runtime\python312._pth') -Encoding Ascii
Write-Output "BUILT $out"

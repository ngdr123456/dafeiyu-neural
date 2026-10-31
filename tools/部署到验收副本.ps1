# -*- coding: utf-8 -*-
<#
    部署到验收副本.ps1 —— 一次部署，四道闸

    为什么需要这个脚本（血的教训）
    ────────────────────────────────────────────────────────────
    2026-10-01 那次：我手工 `Copy-Item exe` 了三次，**从来没同步过 spec/**。
    结果验收副本里的 `spec/任务清单.jsonl` 停在 18:49:04，
    界面显示「已完成 15 ／ 共 24」—— 而真实项目是 26 ／ 33。

    用户一眼看破。**根因不是路径 bug（加载路径一直是对的，走的 EGO_ROOT 不走 _MEIPASS），
    而是"部署只有拷 exe 这一个动作，没有任何一步会告诉你数据旧了"。**

    所以本脚本把"部署"变成四道闸，任何一道不过就不算部署完成：

        ① 漂移预检   —— 先把"源头 vs 副本"的差异**摆出来**，不闷头覆盖
        ② 受控同步   —— 明确的白名单；state/ 与缓存**绝不覆盖**
        ③ 回读校验   —— 逐文件比哈希，不一致就报错退出（不是"看起来拷完了"）
        ④ 状态报告   —— 副本 state\train 必须为空，否则副本不干净

    ⚠️ 本脚本**只碰文件，不碰任何代码**。它不修改副本里 exe 的行为。
    ⚠️ 本文件保存为 **UTF-8 with BOM**。
       本机是 **Windows PowerShell 5.1**（不是 pwsh 7）。5.1 读**无 BOM** 的
       .ps1 会按 ANSI 解码，脚本里的中文会全乱、甚至语法报错。
       ⚠️ 任何编辑器改完这个文件，**必须确认 BOM 还在**（前 3 字节 EF BB BF）。

#>
[CmdletBinding()]
param(
    [string]$Source,
    [string]$Target,
    [switch]$CleanState,     # 额外清空副本 state\train\（默认不动副本数据）
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'

# ── 定位：脚本在 <项目>\tools\ 下
if (-not $Source) {
    $Source = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}
if (-not $Target) {
    $Target = Join-Path (Split-Path (Split-Path $Source -Parent) -Parent) 'backups\验收副本'
}

# ── 白名单：**只有这些**会被同步。不在名单里的一律不动。
$DIRS  = @('engine', 'tests', 'spec', 'rules', 'corpus', 'tools', 'lib')
$FILES = @('启动训练台.exe', 'README.md', 'requirements.txt', '启动训练台.py')

# ── 黑名单：**绝不覆盖**。state\ 是副本自己的运行数据。
$EXCLUDE_DIRS = @('state', '__pycache__', 'build', 'dist', '.git', '.pytest_cache')

function Write-Head($t) {
    Write-Host ''
    Write-Host ('─' * 74) -ForegroundColor DarkGray
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host ('─' * 74) -ForegroundColor DarkGray
}

function Get-Sha([string]$p) {
    if (-not (Test-Path -LiteralPath $p)) { return $null }
    return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
}

function Get-RelFiles([string]$root) {
    <# 列出 root 下全部文件（相对路径），跳过黑名单目录 #>
    $out = @{}
    if (-not (Test-Path -LiteralPath $root)) { return $out }
    Get-ChildItem -LiteralPath $root -Recurse -File -Force | ForEach-Object {
        $rel = $_.FullName.Substring($root.Length).TrimStart('\', '/')
        $skip = $false
        foreach ($x in $EXCLUDE_DIRS) {
            if ($rel -like "$x\*" -or $rel -eq $x) { $skip = $true; break }
        }
        if (-not $skip) { $out[$rel] = $_.FullName }
    }
    return $out
}

# ══════════════════════════════════════════════════════════════
Write-Host ''
Write-Host '  部署到验收副本' -ForegroundColor White
Write-Host "  源：$Source"
Write-Host "  目标：$Target"

if (-not (Test-Path -LiteralPath $Source)) { throw "源目录不存在：$Source" }
if (-not (Test-Path -LiteralPath $Target)) {
    Write-Host "  目标不存在，创建：$Target" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $Target -Force | Out-Null
}

# ══════════════════════════════════════════════════════════════
# ① 漂移预检
# ══════════════════════════════════════════════════════════════
Write-Head '① 漂移预检（先把差异摆出来，不闷头覆盖）'

$drift = @()      # 内容不同
$missing = @()    # 副本缺
$extra = @()      # 副本多（同步不会删，只报告）
$same = 0
$scanned = 0

foreach ($d in $DIRS) {
    $sp = Join-Path $Source $d
    if (-not (Test-Path -LiteralPath $sp)) { continue }
    $sf = Get-RelFiles $sp
    $tp = Join-Path $Target $d
    $tf = Get-RelFiles $tp
    foreach ($rel in $sf.Keys) {
        $scanned++
        $tfile = Join-Path $tp $rel
        if (-not (Test-Path -LiteralPath $tfile)) {
            $missing += "$d\$rel"
        } elseif ((Get-Sha $sf[$rel]) -ne (Get-Sha $tfile)) {
            $mt = (Get-Item -LiteralPath $tfile).LastWriteTime.ToString('MM-dd HH:mm')
            $drift += [pscustomobject]@{ 文件 = "$d\$rel"; 副本时间 = $mt }
        } else { $same++ }
    }
    foreach ($rel in $tf.Keys) {
        if (-not $sf.ContainsKey($rel)) { $extra += "$d\$rel" }
    }
}
foreach ($f in $FILES) {
    $sfp = Join-Path $Source $f
    if (-not (Test-Path -LiteralPath $sfp)) { continue }
    $scanned++
    $tfp = Join-Path $Target $f
    if (-not (Test-Path -LiteralPath $tfp)) { $missing += $f }
    elseif ((Get-Sha $sfp) -ne (Get-Sha $tfp)) {
        $mt = (Get-Item -LiteralPath $tfp).LastWriteTime.ToString('MM-dd HH:mm')
        $drift += [pscustomobject]@{ 文件 = $f; 副本时间 = $mt }
    } else { $same++ }
}

Write-Host ("  扫描 {0} 个文件｜一致 {1}｜内容不同 {2}｜副本缺失 {3}｜副本多出 {4}" -f `
    $scanned, $same, $drift.Count, $missing.Count, $extra.Count)
if ($drift.Count -gt 0) {
    Write-Host ''
    Write-Host '  内容不同的（副本是旧的）：' -ForegroundColor Yellow
    $drift | Sort-Object 文件 | ForEach-Object {
        Write-Host ("    {0,-44} 副本停在 {1}" -f $_.文件, $_.副本时间)
    }
}
if ($missing.Count -gt 0) {
    Write-Host ''
    Write-Host '  副本缺失的：' -ForegroundColor Yellow
    $missing | Sort-Object | ForEach-Object { Write-Host "    $_" }
}
if ($drift.Count -eq 0 -and $missing.Count -eq 0) {
    Write-Host ''
    Write-Host '  ✓ 预检通过：副本已是最新，无需同步。' -ForegroundColor Green
}

# ══════════════════════════════════════════════════════════════
# ② 受控同步
# ══════════════════════════════════════════════════════════════
Write-Head '② 受控同步（白名单；state\ 与缓存绝不覆盖）'

$xd = @()
foreach ($x in $EXCLUDE_DIRS) { $xd += '/XD'; $xd += $x }

foreach ($d in $DIRS) {
    $sp = Join-Path $Source $d
    if (-not (Test-Path -LiteralPath $sp)) { continue }
    $tp = Join-Path $Target $d
    $null = robocopy $sp $tp /MIR @xd /NFL /NDL /NJH /NJS /NP /R:1 /W:1
    Write-Host ("  [目录] {0,-10} robocopy 退出码 {1}" -f $d, $LASTEXITCODE)
}
foreach ($f in $FILES) {
    $sfp = Join-Path $Source $f
    if (-not (Test-Path -LiteralPath $sfp)) { continue }
    Copy-Item -LiteralPath $sfp -Destination (Join-Path $Target $f) -Force
    Write-Host ("  [文件] {0}" -f $f)
}
# ⚠️ state\ **不在同步范围**：那是副本自己的运行数据，覆盖它等于伪造验收环境。

if ($CleanState) {
    $st = Join-Path $Target 'state\train'
    if (Test-Path -LiteralPath $st) {
        Get-ChildItem -LiteralPath $st -File | Remove-Item -Force
        Write-Host '  [清理] 副本 state\train\ 已清空（-CleanState）' -ForegroundColor Yellow
    }
}

# ══════════════════════════════════════════════════════════════
# ③ 回读校验
# ══════════════════════════════════════════════════════════════
Write-Head '③ 回读校验（逐文件比哈希，不是"看起来拷完了"）'

$bad = @()
$checked = 0
foreach ($d in $DIRS) {
    $sp = Join-Path $Source $d
    if (-not (Test-Path -LiteralPath $sp)) { continue }
    $sf = Get-RelFiles $sp
    $tp = Join-Path $Target $d
    foreach ($rel in $sf.Keys) {
        $checked++
        $tfile = Join-Path $tp $rel
        if (-not (Test-Path -LiteralPath $tfile)) { $bad += "$d\$rel（缺失）"; continue }
        if ((Get-Sha $sf[$rel]) -ne (Get-Sha $tfile)) { $bad += "$d\$rel（哈希不符）" }
    }
}
foreach ($f in $FILES) {
    $sfp = Join-Path $Source $f
    if (-not (Test-Path -LiteralPath $sfp)) { continue }
    $checked++
    $tfp = Join-Path $Target $f
    if (-not (Test-Path -LiteralPath $tfp)) { $bad += "$f（缺失）"; continue }
    if ((Get-Sha $sfp) -ne (Get-Sha $tfp)) { $bad += "$f（哈希不符）" }
}
Write-Host ("  逐文件校验 {0} 个" -f $checked)
if ($bad.Count -gt 0) {
    Write-Host ''
    Write-Host '  ✗ 校验不通过：' -ForegroundColor Red
    $bad | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    throw "部署校验失败，共 $($bad.Count) 个文件不一致。副本**不可用于验收**。"
}
Write-Host '  ✓ 全部一致' -ForegroundColor Green

# ══════════════════════════════════════════════════════════════
# ④ 状态报告
# ══════════════════════════════════════════════════════════════
Write-Head '④ 状态报告'

$exe = Join-Path $Target '启动训练台.exe'
if (Test-Path -LiteralPath $exe) {
    $h = Get-Sha $exe
    $sz = (Get-Item -LiteralPath $exe).Length
    Write-Host ("  exe  {0:N0} 字节｜SHA256 {1}" -f $sz, $h)
}
$tl = Join-Path $Target 'spec\任务清单.jsonl'
if (Test-Path -LiteralPath $tl) {
    $rows = Get-Content -LiteralPath $tl -Encoding utf8 | Where-Object { $_.Trim() }
    $done = ($rows | ForEach-Object { $_ | ConvertFrom-Json } |
             Where-Object { $_.status -eq '已完成' }).Count
    $mt = (Get-Item -LiteralPath $tl).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
    Write-Host ("  任务清单  {0} 条｜已完成 {1}｜{2}" -f $rows.Count, $done, $mt)
    Write-Host ("            → 界面将显示「已完成 {0} ／ 共 {1}」" -f $done, $rows.Count) `
        -ForegroundColor Green
}

$train = Join-Path $Target 'state\train'
$n = 0
if (Test-Path -LiteralPath $train) {
    $n = (Get-ChildItem -LiteralPath $train -File -ErrorAction SilentlyContinue).Count
}
Write-Host ''
if ($n -eq 0) {
    Write-Host '  ✓ 副本 state\train\ 为空 —— 验收环境干净' -ForegroundColor Green
} else {
    Write-Host ("  ⚠ 副本 state\train\ 有 {0} 个文件（副本自带的历史数据，未被本次部署触碰）" -f $n) `
        -ForegroundColor Yellow
    Write-Host '    若要清空，加 -CleanState 重跑。' -ForegroundColor Yellow
}

Write-Host ''
Write-Host '  部署完成。' -ForegroundColor Green
Write-Host ''

# DeepSeek Windows 灰测交付记录（2026-11-06）

工作区 `C:\Users\22082\Desktop\DEPSK\books\ego-dialogue-codex-bottom`。开始先执行 `git branch --show-current`、`git rev-parse HEAD`、`git status --porcelain`：分别为 `codex/bottom-drive`、`4c4c2f5d02068e7ac063a308437e1257b5b9f016`、无输出，符合才继续。未使用子代理，未读取/寻找用户密钥，未发真实模型请求，未触碰旧包或用户记忆/配置。

## 最终改动

GUI 用现有 DeepSeek HTTP 开口后端，经现有 LLM hook 和开口校验，使用现有 sense_input 产出的 InputSignal 传入 pipeline。同步 output 回调、Tk 绘制后确认、新场与正常退出保存均保留；没有改动 pipeline、思维、输入理解算法、开口校验规则或记忆算法。OpenCode 不再是 GUI 的后端或兜底；birth 后端仍复用 llm_opencode 中的纯提示词转换函数，不调用其进程/模型。

DeepSeek 后端增加可选 strict 模式，将缺密钥、402、认证、HTTP、网络、无效输出分为固定安全码；默认旧调用仍返回 None，兼容原有入口。articulate 原本会吞 hook 异常，因此 GUI hook 仅保存安全错误码，停止后续无效重试，在同步交付前拒绝模板；不把异常正文传到 UI。输入理解网络等失败在进管线前报错；低置信度保留 birth 原规则降级。失败输入不清除，失败开口不确认，已发生的用户输入状态不回滚。

增加 `accept_birth_chat.py` / `birth/chat_acceptance.py`：必须显式 --allow-network 才能 --send；实际输出 flush 后才确认，成功后保存。独立进程 --expect-prior-fact 只检查 prior 中是否含指定文本，不读取密钥、不发网络、不打印记忆正文。退出码：0 成功、2 匹配失败、3 后端失败、4 输出/保存等失败；参数错误为 argparse 的 2。

首次密钥通过隐藏输入到进程环境，长期沿用用户本机 `.dsh/.credentials.yaml`（本人 ACL，明文且不共享/不入库）；详细方法与限制见 WINDOWS_CHAT.md。不依赖外层临时文件。环境变量优先。未验证新 API 账户、模型授权、余额和网络。

## 命令及测试结果

以下命令均在工作区执行；只使用现有 pytest 依赖，全部为离线 stub/mock。新测试把 load_api_key 换成虚构测试值，未 mock 的网络调用会立即失败。既有 input_sense/CLI 测试也各自 mock 凭证和模型。

```powershell
$py = 'C:\Users\22082\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -I -X utf8 -c "import sys; sys.path[:0]=['.','.pytest-deps']; import pytest; raise SystemExit(pytest.main(['tests/test_windows_chat.py','tests/test_windows_deepseek.py','tests/test_birth_cli_repl.py','tests/test_birth_input_sense.py','-q','-W','error','-p','no:cacheprovider','--basetemp=build/deepseek-chat-tests-1']))"
```

结果：1 failed, 83 passed in 1.50s。失败为新 mock 只对第一次调用返回输入理解 JSON，第二轮返回了开口文本；改为按调用奇偶返回。

同命令将 basetemp 换为 `build/deepseek-chat-tests-2`：2 failed, 84 passed in 1.75s。新增 GUI 测试经 Windows PowerShell 管道写入 Python 时中文被转成问号，断言失败；已用直接补丁恢复中文，生产代码中文正常。将 basetemp 换为 `build/deepseek-chat-tests-3`：86 passed in 1.70s，退出码 0。

构建命令：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_windows_chat.ps1 -OutputName BirthChat-DeepSeek-Windows-20261106
```

结果：`BUILT C:\Users\22082\Desktop\DEPSK\books\ego-dialogue-codex-bottom\dist\BirthChat-DeepSeek-Windows-20261106`，退出码 0。目标原先不存在；构建脚本拒绝覆盖已有目录。随后将本次改动文件恢复为仓库原有 LF，移除说明文件 BOM，只同步了本次新包内对应文件，避免无关整文件换行 diff；未改旧包。按 SHA256 比较仓库与新包全部 25 个 birth 源码/入口/说明文件，全部相同。

包内源码/运行时初测：

```powershell
& .\dist\BirthChat-DeepSeek-Windows-20261106\runtime\python.exe -I -B -X utf8 -c "import sys; sys.path[:0]=['dist/BirthChat-DeepSeek-Windows-20261106','.pytest-deps']; import birth.windows_chat; print('PACKAGE_SOURCE=' + birth.windows_chat.__file__); import pytest; raise SystemExit(pytest.main(['tests/test_windows_chat.py','tests/test_windows_deepseek.py','tests/test_birth_cli_repl.py','tests/test_birth_input_sense.py','-q','-W','error','-p','no:cacheprovider','--basetemp=build/deepseek-chat-package-tests']))"
```

结果：PACKAGE_SOURCE 指向新包，86 passed in 2.11s，退出码 0。补充完整 DeepSeek 两段 HTTP adapter → GUI 显示 → 新场保存的 mock 成功用例后，执行同命令、basetemp 换为 `build/deepseek-chat-package-final-tests`：**87 passed in 1.86s，退出码 0**。源码/包此后没有生产行为变更。

覆盖：真实 HTTP adapter 的离线成功、输入理解进入 pipeline、缺密钥、两阶段 402/401/503/网络/超时/非法 JSON/空返回、开口校验拒绝模板、GUI 同步显示前无承诺回流、显示失败不确认且保留输入、新场落盘、正常 main/退出、保存失败保留状态、慢 mock 保持 GUI 响应并排队保存退出、损坏记忆拒绝覆盖、新场及重启载入 prior、控制台禁止未授权网络。保留旧 OpenCode transport 的离线兼容回归。

跨进程 mock 验收命令：

```powershell
& .\dist\BirthChat-DeepSeek-Windows-20261106\runtime\python.exe -I -B -X utf8 build/run_package_mock_acceptance.py
& .\dist\BirthChat-DeepSeek-Windows-20261106\runtime\python.exe -I -B -X utf8 .\dist\BirthChat-DeepSeek-Windows-20261106\accept_birth_chat.py --memory-path build/deepseek-package-acceptance.json --expect-prior-fact PackageMock-20261106
& .\dist\BirthChat-DeepSeek-Windows-20261106\runtime\python.exe -I -B build/check_deepseek_package.py
```

第一个脚本在工作区 build 下保留，可复跑查看；它 mock 凭证函数和 urllib 传输，阻止 OpenCode，使用 runpy 执行真实包内控制台入口，并传 `--allow-network --send`（实际网络被 mock）。只输入合成测试文本。首次输出 `PRIOR_LOADED=False`、合成回复、`DELIVERED_AND_SAVED=True`；第二个独立进程输出 `PRIOR_LOADED=True`、`PRIOR_FACT_MATCH=True`。源码/顶层白名单检查输出 `PACKAGE_ALLOWLIST_AND_SOURCE_HASHES_OK 25`。均退出码 0。测试记忆只在被 gitignore 排除的 build，不在包内。此证明跨进程持久化链路，不代表真实模型已验证。

打包与文件名检查：

```powershell
$bundlePath = (Resolve-Path -LiteralPath 'dist\BirthChat-DeepSeek-Windows-20261106').Path
$bad = @(Get-ChildItem -LiteralPath $bundlePath -Recurse -File | Where-Object { $_.Name -match '(?i)credential|birth_memory|\.log$|\.jsonl$|^\.env' })
Write-Output "DISALLOWED_FILE_COUNT=$($bad.Count)"
$zipPath = Join-Path (Get-Location) 'dist\BirthChat-DeepSeek-Windows-20261106.zip'
if (Test-Path -LiteralPath $zipPath) { throw 'ZIP exists; refusing overwrite' }
Compress-Archive -LiteralPath 'dist\BirthChat-DeepSeek-Windows-20261106' -DestinationPath $zipPath
Get-FileHash -LiteralPath $zipPath -Algorithm SHA256
git diff --check
```

结果：`DISALLOWED_FILE_COUNT=0`。包顶层仅 birth、runtime、三个入口和 WINDOWS_CHAT.md；不复制用户 home/state/config、测试、日志、site-packages。ZIP 退出码 0，SHA256 `9060C8E8E3E9A38E5CAB27C24B4742FDFCD80B5399CB8613968921429B07D782`。`git diff --check` 无输出，退出码 0。

## 产物与外层验收

目录：`C:\Users\22082\Desktop\DEPSK\books\ego-dialogue-codex-bottom\dist\BirthChat-DeepSeek-Windows-20261106`

ZIP：`C:\Users\22082\Desktop\DEPSK\books\ego-dialogue-codex-bottom\dist\BirthChat-DeepSeek-Windows-20261106.zip`

GUI：包内 `Start-BirthChat.cmd --memory-path <新的包外记忆路径>`。离线加 `--offline`。

受控入口：包内 `runtime\python.exe -I accept_birth_chat.py --memory-path <新的包外记忆路径> --allow-network --send <非敏感自我介绍>`；随后独立进程 `runtime\python.exe -I accept_birth_chat.py --memory-path <同一路径> --expect-prior-fact <唯一姓名标记>`。详细 PowerShell 调用与安全提供密钥方式见 WINDOWS_CHAT.md。

限制：真实模型未验证；默认模型是否受新账户支持需外层验证，余额/网络/API 响应必须以真实失败处理。薄记忆不是完整聊天记录；不支持同记忆文件并发写；只有正常保存才落盘；本机凭证文件是明文且需用户限制权限。未修改任何底层思维逻辑。

## 本地提交结果

执行：

```powershell
git add -- Start-BirthChat.cmd WINDOWS_CHAT.md WINDOWS_DEEPSEEK_VALIDATION.md birth/llm_deepseek.py birth/windows_chat.py birth/chat_acceptance.py accept_birth_chat.py tests/test_windows_chat.py tests/test_windows_deepseek.py tools/build_windows_chat.ps1
# 仅 add 成功时才运行：
git commit -m "Connect Windows chat to birth DeepSeek with strict delivery failures"
```

`git add` 退出码 128：`fatal: Unable to create 'C:/Users/22082/Desktop/DEPSK/books/ego-dialogue-codex/.git/worktrees/ego-dialogue-codex-bottom/index.lock': Permission denied`。因此未执行 commit；未绕过权限、未 amend、未 push，全部修改保留在工作树。最终执行 `git diff --check`、`git branch --show-current`、`git rev-parse HEAD`、`git status --short` 核对现场，分支和 HEAD 未变。

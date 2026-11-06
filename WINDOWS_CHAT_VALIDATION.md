# Windows 灰测交付记录（2026-11-06）

提交前基线：分支 `codex/bottom-drive`；HEAD `9c8b42f82a03e5d4da1dbc11925557a1b11a4125`；`git status --porcelain` 无输出。只在指定工作树写入，没有修改主仓源码，没有 push / amend。

新增文件：`birth/windows_chat.py`、`start_birth_chat.pyw`、`Start-BirthChat.cmd`、`tools/build_windows_chat.ps1`、`tests/test_windows_chat.py` 和两份 WINDOWS_CHAT 说明。既有代码只修改 `birth/llm_opencode.py` 的 Windows 传输兼容：临时目录、UTF-8、隐藏子进程；未修改 pipeline、记忆、动力、组织、立场及开口校验逻辑。

已核对：`birth/__main__.py` CLI 的 REPL 默认开记忆、首轮新场、默认输入感知；`pipeline.turn(output=...)` 必须在 output 同步正常返回后才确认台词及承诺等副作用，输入本身不回滚；`end_session()` 保存、`_persist_and_reset_session()` 先保存再清场并载入 prior。GUI 直接复用这些契约。

环境：PATH 上的 Python 商店占位不可运行，旧 venv 不可运行。发现可用的 CPython 3.12.14：`C:\Users\22082\.cache\codex-runtimes\codex-primary-runtime\dependencies\python`；Tk 实际建窗、刷新、销毁输出 `TK_START_OK`。运行时已随包交付。未安装 PyInstaller，不需要它或其他第三方运行依赖；定向测试使用工作树已有 `.pytest-deps`，不随包分发。

构建命令（工作目录为仓库根）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/build_windows_chat.ps1
```

实际输出：`BUILT C:\Users\22082\Desktop\DEPSK\books\ego-dialogue-codex-bottom\dist\BirthChat-Windows`。本机默认执行策略不允许运行 ps1，构建只对当前子进程设置 Bypass，没有修改系统策略。

最终定向验证使用包内 Python、包内源码，并将警告视为错误：

```powershell
& .\dist\BirthChat-Windows\runtime\python.exe -I -X utf8 -c "import sys; sys.path[:0]=['dist/BirthChat-Windows','.pytest-deps']; import pytest; raise SystemExit(pytest.main(['tests/test_windows_chat.py','tests/test_birth_cli_repl.py','-q','-W','error','-p','no:cacheprovider','--basetemp=build/chat-final-tests']))"
```

实际输出：`................................ [100%]` / `32 passed in 1.24s`，退出码 0。全程离线 stub/mock，不代表真实模型实测。覆盖实际 main/Tk 事件循环、发送控件、birth.turn、显示之前无回流、显示失败不确认且保留输入、新场保存并载入 prior、正常结束保存、磁盘失败保留窗口和状态、慢 mock 后端时 UI 响应且等待保存退出、默认后端拒绝模板、损坏记忆不覆盖、OpenCode Windows 子进程参数。

实际双击等价启动：由 `cmd.exe /d /c` 执行包内 `Start-BirthChat.cmd --offline --memory-path <工作树 build 下隔离文件>`，观察到包内 `pythonw.exe` 进程的非零主窗口句柄和标题 `第一期 · 聊天 [离线模板验证]`。使用正常窗口关闭请求，返回 True，进程在 5 秒内退出。输出 `CMD_LAUNCH_WINDOW_OK (offline; bundled pythonw.exe)`、`CLOSE_REQUEST_ACCEPTED True`；此观察方式未取得退出码，不将其记作 0。初次通过 WMI 观察进程被系统权限拒绝，随后用已启动程序的路径和进程句柄核对。

包内文件名排查：凭证、birth_memory.json、.log、.jsonl、.env 匹配数为 0。构建源文件使用白名单，不复制用户 home、state、环境文件、site-packages 或测试数据。包目录及 ZIP 位于被 gitignore 排除的 `dist/`，测试状态仅位于被排除的 `build/`。

真实模型状态：没有发起任何真实模型请求，尤其没有再次请求 DeepSeek。原 birth 配置为 DeepSeek `deepseek-flash` 优先、OpenCode `opencode/deepseek-v4.1-flash-free` 兜底；没有发现 BIRTH 环境覆盖，也没有在 PATH 找到 opencode。GUI 明确停用 DeepSeek，使用现有 OpenCode 钩子和原开口校验，但需要本机非 DeepSeek 模型配置；没有可安全验证的替代后端，真实对话未验证。输入感知因只支持 DeepSeek 而明确降级为原有规则。没有读取、输出或打包任何密钥。

交付路径：`C:\Users\22082\Desktop\DEPSK\books\ego-dialogue-codex-bottom\dist\BirthChat-Windows\Start-BirthChat.cmd`；整目录及旁边的 `BirthChat-Windows.zip`。默认模式可启动界面，后端缺失时明确提示；真实模型可用性仍是缺口。记忆为原有薄记忆、非完整聊天归档；正常退出/新场才落盘；不支持多个实例同时写同一个记忆文件。

版本交付：`git diff --check` 通过。尝试按明确文件清单执行 `git add`，返回 `fatal: Unable to create 'C:/Users/22082/Desktop/DEPSK/books/ego-dialogue-codex/.git/worktrees/ego-dialogue-codex-bottom/index.lock': Permission denied`。因此未能暂存和创建本地独立 commit；没有改动权限、没有 push、没有 amend，工作树保留供接手。提交前后 HEAD 均为 `9c8b42f82a03e5d4da1dbc11925557a1b11a4125`。交付 ZIP SHA256：`D6008513F43C6F489C72976B9B2027D8D19B98095958C65865419D158A1DDC5E`。

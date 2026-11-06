# 第一期 Windows 灰测聊天

双击 `dist\BirthChat-Windows\Start-BirthChat.cmd`。整份文件夹可移动；附带 CPython 3.12 和 Tk，无需安装 Python 或 pip 包。运行时许可证位于 `runtime\LICENSE.txt`。这不是单文件 exe。源码入口是 `start_birth_chat.pyw`，不使用旧 `launcher.py` 或 engine。

输入后点击“发送”，或 Ctrl+Enter；Enter 换行。“结束本场 / 新场”立即保存薄记忆并开始新场；“保存并退出”和右上角关闭先保存再退出。后端忙时窗口仍可操作，退出会等待本轮；保存失败保留原窗口和内容，可重试。失败的输入留在输入框。不要用任务管理器强杀来结束会话。

默认走原有 OpenCode 后端及 birth 的开口校验。此前 DeepSeek 402，本灰测入口停用 DeepSeek（包含其输入感知），也拒绝名称含 deepseek 的 OpenCode 模型；输入感知明确降级为 birth 原有规则。未修改第一期动力、立场、仲裁、记忆提取行为。默认不使用模板替代真实模型；后端缺失、无响应或校验失败会显示失败，模板不会确认回流。某些第一期内部保护路径主动返回模板时，本入口同样提示未交付。

真实聊天需本机安装并配置现有 `opencode` 命令，以及环境变量 `BIRTH_OPENCODE_MODEL` 指定已获授权的非 DeepSeek 模型。沿用 OpenCode 自己的本机凭证和环境，不在界面输入密钥。应用不会修改模型账户配置，也不附带凭证。目前未提供经过真实对话验证的可用模型，见验证记录。因此此交付可直接打开界面，但本机后端未就绪时不能完成真实聊天。

记忆沿用 `BIRTH_MEMORY_PATH`，未设置则为 `%USERPROFILE%\.dafeiyu\birth_memory.json`。只保存原有最近场次的薄痕，不保存完整聊天记录；界面显示的本场记录会在窗口关闭后消失。新场保留窗口里的历史以便核对。程序和包均不携带已有记忆。不要同时打开多个实例使用同一个记忆文件，也不要把记忆文件指向发布包或版本库。

离线验证（界面标注“非真实模型”，不会请求网络）：

```powershell
.\dist\BirthChat-Windows\runtime\python.exe -I .\dist\BirthChat-Windows\start_birth_chat.pyw --offline --memory-path "$env:TEMP\birth-chat-offline.json"
```

有 Python 3.12+ 和 Tk 时也可运行 `python -m birth.windows_chat`。构建：`powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_windows_chat.ps1 -PythonRoot <含Tk的CPython目录>`（仅当前构建进程允许脚本，不改系统策略）。构建脚本只复制 birth 源码、入口、说明和标准运行时，不复制第三方 site-packages；已有目标目录时拒绝覆盖。`dist/` 不入库。打包无需 PyInstaller。

输出确认契约：管线在工作线程运行，同步 output 回调把结果排入主线程；主线程插入完整文本并执行 Tk 的绘制刷新后才唤醒回调。输出失败抛异常，不确认该句承诺、悬问等回流；用户输入等管线已发生的状态保留。窗口最小化而无法显示时拒绝确认，恢复后可重试。正常退出和新场调用原有保存路径；失败不清场、不销毁窗口。

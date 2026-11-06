# Windows DeepSeek 灰测聊天

新交付目录：`dist\BirthChat-DeepSeek-Windows-20261106`。双击其中的 `Start-BirthChat.cmd`；整份文件夹可移动，自带 CPython 3.12、Tk 和 birth 源码，无需 Python、pip 或 OpenCode。许可证在 `runtime\LICENSE.txt`。旧包不覆盖。本交付只经过离线 mock，真实模型由外层受控验收。

默认使用 birth 现有 DeepSeek HTTP 后端和输入理解，之后仍由原动力、立场、组织、仲裁、开口校验和记忆提取处理。普通成功轮次通常有输入理解和开口两次请求；开口校验可能重试。输入理解低置信度沿用 birth 的规则降级；连接故障、额度不足、身份验证错误、无效返回都会报错，不交付模板、不转 OpenCode。某些原有内部保护路径直接生成模板时，界面也拒绝确认并提示校验失败。

输入后点“发送”或 Ctrl+Enter；Enter 换行。“结束本场 / 新场”先保存再清场。“保存并退出”和右上角关闭先保存再退出；忙时等待当前轮完成。失败输入保留；保存失败保留窗口和当前场，可重试。输出只有在主线程插入完整文本并刷新绘制后才同步确认；显示失败不记为已说，不回流该句承诺或悬问。最小化无法显示时也拒绝确认。用户输入引起的原有状态更新不回滚。

## 首次提供密钥

程序只使用 `DEEPSEEK_API_KEY` 环境变量（优先），否则沿用 birth 的 `%USERPROFILE%\.dsh\.credentials.yaml`。不在聊天框、命令行参数、仓库或包内填密钥。无需外层临时文件。本轮开发没有读取或寻找本机密钥，也没有发真实模型请求。

首次可在 PowerShell 隐藏输入，只给本次启动及子进程使用；命令历史不含明文密钥，也不打印密钥：

```powershell
$secret = Read-Host 'DeepSeek API key' -AsSecureString
$env:DEEPSEEK_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
try {
  & '.\dist\BirthChat-DeepSeek-Windows-20261106\runtime\python.exe' -I '.\dist\BirthChat-DeepSeek-Windows-20261106\start_birth_chat.pyw'
} finally {
  Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
  $secret.Dispose()
}
```

## 长期使用

若已有上述本机凭证文件，沿用即可。若新建，由用户在仓库及包外的 `%USERPROFILE%\.dsh` 创建 `.credentials.yaml`，通过本机编辑器填入一行 `DEEPSEEK_API_KEY: "自己的密钥"`。先对空文件设置权限，再填写：“属性 → 安全 → 高级”关闭继承、移除其他普通账户，只保留本人和必要的系统管理账户。它是明文文件，应置于本机非共享、非同步备份目录；勿截图、提交仓库或放入发行包。birth 当前没有 Windows 凭据管理器加密存储支持。不要用含真实密钥的 shell 命令创建文件。长期也可每次按上面的隐藏输入方式启动。

环境变量优先于文件；更换文件中的密钥后若仍存在旧环境变量，需由用户清除或更新。两种方式均需要信任当前 Windows 账户及其进程。应用不保存密钥、不输出后端异常正文、不修改账户配置。

模型沿用 birth 默认及 `BIRTH_DEEPSEEK_MODEL` / `DEEPSEEK_MODEL`；地址沿用 `BIRTH_DEEPSEEK_BASE_URL` / `DEEPSEEK_BASE_URL`，默认 `https://api.deepseek.com`，只应使用本人信任的 HTTPS 服务地址。界面不显示这些可配置值，防止意外泄露。未验证新账户对默认模型的支持；外层可先设置已授权的模型。开口超时默认 60 秒、输入理解默认 12 秒，可用 `BIRTH_DEEPSEEK_TIMEOUT`、`BIRTH_SENSE_TIMEOUT` 调整。

## 记忆与独立验收

记忆沿用 `BIRTH_MEMORY_PATH`，未设置则为 `%USERPROFILE%\.dafeiyu\birth_memory.json`。仅保存最近场次薄痕，不是完整聊天归档。包不包含已有记忆。灰测请显式指定新的包外路径；不要同时运行多个实例写同一文件。正常新场/退出才保存，勿强杀进程。

外层 GUI 真实验收：配置本机密钥后运行下列命令，发送带唯一姓名标记的自我介绍，观察真实回复，正常保存退出；用同一命令重启，询问“你还记得我是谁吗？”。这会实际调用模型及产生费用，本轮开发没有执行：

```powershell
.\dist\BirthChat-DeepSeek-Windows-20261106\Start-BirthChat.cmd --memory-path "$env:LOCALAPPDATA\BirthChatGrey\acceptance-memory.json"
```

可控控制台入口供外层只做一次真实聊天，之后在独立进程离线核对持久化记忆已加载：

```powershell
$bundle = '.\dist\BirthChat-DeepSeek-Windows-20261106'
$memory = "$env:LOCALAPPDATA\BirthChatGrey\acceptance-console.json"
# 仅此条显式授权真实网络；打印回复并 flush 成功才确认，随后保存。
& "$bundle\runtime\python.exe" -I "$bundle\accept_birth_chat.py" --memory-path $memory --allow-network --send '我叫灰测小舟，今天想聊月亮。'
# 新进程，只读入 prior，不读取密钥、不发网络、不输出记忆正文。
& "$bundle\runtime\python.exe" -I "$bundle\accept_birth_chat.py" --memory-path $memory --expect-prior-fact '灰测小舟'
```

成功标志分别为 `DELIVERED_AND_SAVED=True`、`PRIOR_LOADED=True`、`PRIOR_FACT_MATCH=True`，退出码 0。缺少 `--allow-network` 不允许发送。匹配失败退出码 2，后端失败 3，输出/保存等失败 4；失败不能认作成功。离线匹配仅证明薄记忆被重启加载，模型是否正确运用记忆仍需 GUI 真实问答。使用非敏感灰测内容，不将真实聊天输出重定向到发行包。

离线 GUI 验证：给 GUI 命令加 `--offline`，界面标注“非真实模型”，不会请求模型，不代表真实验收。

## 重建

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_windows_chat.ps1 -OutputName BirthChat-DeepSeek-Windows-20261106
```

可传 `-PythonRoot <含Tk的CPython目录>`。目标存在时拒绝覆盖，后续重建换新 `-OutputName`，直接运行新包内入口。构建按白名单复制 birth 的 `.py`、三个入口、说明和标准运行时，排除状态、凭证、日志、测试和 site-packages；`dist/` 不入库。

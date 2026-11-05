# LOCAL_RETRIEVAL_V1

出处：出生必备第 3 条体验通道／薄记忆。本 sidecar 从既有记忆账本提供候选，不写入、删除或覆盖账本；不判断问题是否已答或承诺是否兑现，不接入 pipeline、articulate，也不改变台上话术和既有判定。

## 数据与索引

只读取显式 `--ledger`（API 的 `ledger_path`），通过 `BirthMemoryStore(ledger_path).list_sessions()` 取得会话，不扫描其他目录。索引 `facts`、`commitments_pending`、`commitments_resolved`、`open_questions`、`her_questions` 和 `stance_traces` 的 `point`、`why`，分别标为 `stance_traces.point`、`stance_traces.why`；按零起始 `session_index`、`field`、原始文本精确去重，跳过空白文本，保留 `ended_at`。立场记录以 `list_sessions()` 实际返回结果为准。

默认索引与账本同目录，名称为 `<ledger_stem>.vec.sqlite3`。索引是独立 SQLite 文件：

- `meta`：键值对，保存 `schema_version`、`model`、`dim`、`ledger_path`、`ledger_sha256`、`ledger_size`、`built_at`、`rows`。
- `memory_items`：`id`、`session_index`、`field`、`text`、`ended_at`，按场次、字段和文本唯一。
- `vec_items`：sqlite-vec `vec0`，rowid 对应 `memory_items.id`，非空索引维度来自 embedder 的 `embedding_size`。空索引无需加载模型，`dim=0`，vec0 使用 1 维占位且没有向量。

构建为全量重建：先在索引同目录创建临时数据库、写入并提交，核对账本在读取和构建期间未改变，再用 `os.replace` 原子替换。账本指纹、路径、schema、模型及非空索引维度匹配且未指定 `--force` 时不重建。检索默认在索引缺失或过期时重建，`--no-rebuild` 则报 `IndexStale`。`status` 不加载模型，其过期判断基于账本、schema 和模型名；实际维度在构建或非空检索时核对。账本不存在或为空时索引行数为零，检索返回空列表。

构建失败会清理临时文件，保留已有索引；账本不会被写入。依赖或模型不可用时抛 `RetrievalUnavailable`，不会退回词表、其他相似度算法或假结果。CLI 错误以 JSON 输出并返回非零状态。账本读取遵循 `BirthMemoryStore` 的现有容错行为。

## 本机环境与使用

2026-11-05 本机验证：Python 3.12.10、sqlite-vec 0.1.9（Windows amd64，`vec_version` 为 v0.1.9）、fastembed 0.9.1、onnxruntime 1.29.0、numpy 2.5.2。默认模型 `BAAI/bge-small-zh-v1.5` 为 512 维，`model_optimized.onnx` 大小 94,781,076 bytes。模型目录包含 `config.json`、`ort_config.json`、`special_tokens_map.json`、`tokenizer.json`、`tokenizer_config.json`、`vocab.txt` 和该 ONNX 文件。

沙箱不能写用户 site-packages；本机依赖位于 `build/retrieval-deps`，模型位于 `build/retrieval-model-local`。代码不硬编码依赖目录；测试和 CLI 由外部设置 `PYTHONPATH`，例如 PowerShell：

```powershell
$env:PYTHONPATH = "$(Join-Path (Get-Location) 'build/retrieval-deps');$(Get-Location)"
python -m birth.retrieval build --ledger path/to/birth_memory.json --model-dir build/retrieval-model-local
python -m birth.retrieval status --ledger path/to/birth_memory.json
python -m birth.retrieval search --ledger path/to/birth_memory.json --model-dir build/retrieval-model-local --k 5 "周末要讲的故事"
python -m birth.retrieval build --ledger path/to/birth_memory.json --model-dir build/retrieval-model-local --force
python -m birth.retrieval search --ledger path/to/birth_memory.json --no-rebuild --model-dir build/retrieval-model-local "周末"
```

可用 `--index` 指定独立索引路径，`--model` 选择模型；指定 `--model-dir` 时传给 fastembed 的 `specific_model_path`，否则由 fastembed 根据 `--cache-dir` 管理缓存及下载。搜索 `k` 范围为 1–50，结果仅含 `text`、`field`、`session_index`、`ended_at` 和向量距离。

## 测试口径与限制

`tests/test_birth_retrieval.py` 默认使用确定性假 embedder 和临时账本，依赖 sqlite-vec，但不需要网络。真实中文模型测试仅在 `BIRTH_RETRIEVAL_REAL=1` 时运行，模型目录优先取 `BIRTH_RETRIEVAL_MODEL_DIR`，否则使用 `build/retrieval-model-local`；目录不存在时跳过。使用外部提供的真实 Python 解释器及 `PYTHONPATH` 运行测试。

当前只支持全量重建，没有增量更新或语义重排；首次下载模型需要网络／代理。索引是候选副本，本身不包含账本写权限；调用侧仍应自行保证文件系统权限与隐私。

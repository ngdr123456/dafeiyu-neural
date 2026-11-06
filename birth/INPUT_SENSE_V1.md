# 输入感知 V1

出处：规格页「出生必备·感知与对象感」和「第一期」第 2 条。

本刀只用项目已有 DeepSeek 薄客户端的配置与密钥读取，模型产出 act、addressee、confidence、scope；确定性映射仍在 input_contract。仅 scope=conversation 的 pause/stop 前移 S1b；task 作用域映射 S15 请求，unclear 不猜停。缺 scope 的旧模型输出按 unclear 兼容读取，非法 scope 显式 degraded。self/unclear 对象不产 pursue。结果不写记忆，只在 TurnResult.input_signal 返回。普通入口默认开启；--stub 或 --no-sense 关闭；turn 直调默认关闭，可用 BIRTH_INPUT_SENSE 开启。

降级时保留非空 source 和 provenance，不提供动力线索：

| reason | 原因 |
| --- | --- |
| no_key | 无密钥 |
| timeout | 请求超时 |
| network | 网络错误 |
| http_<status> | HTTP 错误 |
| invalid_json | JSON 无法解析 |
| invalid_output | 字段缺失或枚举越界 |
| low_confidence | 低置信度 |

验收：依次运行 `python -m pytest -q tests/test_birth_input_sense.py`、`tests/test_birth_input_contract.py`、`tests/test_birth_brief_shape.py`、`tests/test_birth_drive_structured.py`、`tests/test_birth_phase1.py`、`tests/test_birth_cli_repl.py`、`tests/test_birth_multiturn_loop.py`（后六项同样使用 `python -m pytest -q`）。真模型另运行 PowerShell `$env:BIRTH_LIVE_SENSE='1'; python -m pytest -q -s tests/test_birth_input_sense.py`。

FALSE_GREEN：手工传 input_signal 不算验证普通入口；离线测试仅替换网络层，不替换整个感知函数；真模型是否运行及其实际返回必须单独记录。

已知未覆盖风险：只看当前一句，模型可能误判；每轮一次模型调用带来延迟和成本；发送至 DeepSeek 会产生数据出域。

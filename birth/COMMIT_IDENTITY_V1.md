# COMMIT_IDENTITY_V1：承诺回流的身份与推迟

出处：出生必备第 3 条体验通道；续接 PRIOR_COMMIT_RESOLVE_V1 的已知边界。实测跨场催「我答应你周末讲那个故事」，推迟回声被提取为新债，§6 guard 阻挡下一轮催原债；同场催「同场说好晚点聊月亮」，推迟回声既凭主题重叠销原债又被提取为新债。

债的身份由产生轮的结构位置决定，不由文字形状、关键词黑名单、相似度或编辑距离判断。催债帧的承诺形状是推迟或重述候选；无法辨别时保留候选，不升级成债、不挡原债、不销原债。用户明说已了仍可销；非催债轮照旧记独立债。

结构判据：press_commit 且 prior pending 非空，且 drive_prior_press_pending 或 drive.why 含「上场承诺｜」，为 prior_press；否则 commit_deliverable 与 commit_deliver_intent 同真且同场 pending 非空，为 same_session_press。prior target 取 pressed_commitment，同场取 recognized_same_commitment；动作帧未识别时可回落队头，其余无帧。销账独立读认账身份，不能沿此回落规则误销多笔。

CommitmentCandidate 包含 text、target、frame、source，放在 ThinContext 与 PriorSessionTrace 的 commitment_candidates 工程师通道，不参与 say_intent、drive、meaning、org 或台上表达。开口后先提取与识别帧；用户明说已了优先销账；候选否决同场交付推断。无帧照旧入债，有帧而 target 未销则留候选，target 本轮已销则不留回声。销账或清空时清对应候选；按四字段精确去重，限最近 20 条。

持久化记录候选并以 max_commits 截尾；老文件缺字段视为空，非法条目丢弃。导出合并 prior 与本场候选，去重并仅留 target 仍在合并 pending 中的条目；读写盘同样过滤悬空候选；候选绝不并入 pending。pending 独立容量与显式溢出见 MEMORY_V1。

测试清单：跨场真推迟及第三场延续；同场推迟；非催债独立承诺；无法辨别的候选；用户明确已了；多债队头；无债立债；结构判据、泄漏拦截、落盘兼容、复制与销账清理；既有回归文件逐一运行。

边界：同场交付判定中的主题重叠仍是兼容路径；本轮 utterance 提取到承诺形状时否决它；真交付若也带承诺壳会保守留债，等用户明说已了。不接检索或向量，不扩 extract 词表，不 push。

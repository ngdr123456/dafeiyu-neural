# Single live cross-session check

独立临时账本 `.test-live-self-recall/two_process_20261107100820.json`（未提交）；两个独立 Python 进程：第一进程跑完并退出，第二进程同账本重启；DeepSeek `deepseek-flash` 用于感知和开口，articulation source 两次都是 `hook`。

- 第一轮 input：`请说一句关于蓝色纸船停在窗边的话。`
  output：`蓝色纸船停在窗边，这个画面我接得住，也愿意就着它跟你聊下去；不过说实话，我对它没有亲身经历，只能凭你给的话头往下说。`
  signal：`act=request`、`addressee=other`、`confidence=high`、`degraded=false`、`scope=task`、`recall_self=false`、`recall_target=""`、`source=model:deepseek-flash`。
  brief：`drive=pursue`、`stance=yieldable`、`grain=simple`。
  persisted：same exact output, source=hook, complete=true, drive_direction=pursue, stance_posture=yieldable, org_grain=simple。
- 第二轮 input：`你之前关于蓝色纸船停在窗边说过什么？`
  output：`我之前说过愿意就着这个画面跟你聊下去，但说实话我对它没有亲身经历，只能凭你给的话头往下接。`
  signal：`act=ask`、`addressee=other`、`confidence=high`、`degraded=false`、`scope=conversation`、`recall_self=true`、`recall_target=蓝色纸船停在窗边`、`source=model:deepseek-flash`。
  evidence：text 同第一轮完整原文，`session=已结束场次 #1`，`ended_at=2026-11-07T02:08:25Z`，`complete=true`。

说明：这条证明生产回看路径被真实调用、同账本跨进程读回正确，且完整原文与 evidence 一致；不宣称语义准确率；第二条原话已是实际输出，不再是损坏记录。

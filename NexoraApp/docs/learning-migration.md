# HarmonyosApp 学习接口迁移

本次落点是 NexoraApp。教材阅读、学习助手、复习与系统入口共用登录后配置的 Learning 服务地址与用户名。

## 已接通的链路

| 范围 | 实现 | 关键行为 |
| --- | --- | --- |
| A0 坐标 | `common/LearningApi.ets`、`common/ReaderPaginator.ets` | 解析段落 `start/end`、章节 `chapterRange/coordinateSpace`；分页保留码点坐标、空白和完整代理对。 |
| A1 会话与队列 | `common/LearningReading.ets`、`common/LearningReadingApi.ets` | 每章每次访问独立会话；只统计可记录时间，同页连续停留两秒后计覆盖；Preferences 持久化，按服务和账号隔离。 |
| A2 生命周期 | `components/learning/LearningReader.ets`、`entryability/EntryAbility.ets`、`pages/MainChat.ets` | 翻页切章、目录跳章、前后台、浮层、十秒心跳和退出均接入；登录及打开学习时补发。 |
| A3 遥测 | `common/LearningReadingApi.ets` | 发送 `focus_in/focus_out/snapshot/session_complete/ask`，附会话、有效时长和课程；失败丢弃。 |
| A4 教材完成 | `components/learning/LearningReader.ets` | 每章末尾显式确认；空间不够则补末页；先保存快照再调用教材完成接口。翻到下一章不会自动完成上一章。 |
| A5 阅读问答 | `components/learning/LearningReader.ets` | 顶栏“问 AI”、半屏面板、当前页正文上下文、现有 Markdown 渲染；换章和离开后丢弃旧答案。 |
| A6 读后复习 | `components/learning/LearningReader.ets`、`components/agent/LearningAgentReview.ets` | 只在目标章明确完成后，退出时发送 `reading_done`；完成响应晚于退出也可衔接，题目就绪后进入小测。 |
| B1 组件复用 | `LearningApi.resolveReaderTarget`、`components/agent/LearningAgent.ets` | 学习助手自己的导航栈直接挂载阅读器，返回保留下面的时间线或作答页。 |
| B2 入口互跳 | `components/agent/` | 时间线、计划和先修卡进阅读器；小测、今日复习、认知报告各自保留；“去学习”打开现有学习工作区。 |
| B3 系统入口 | `EntryAbility`、`MainChat`、`Index`、`intents/`、`entryformability/` | `nx_route/decision_id` 统一排队；登录校验及服务配置成功后消费；意图打开 day/review，服务卡片直接回写决策。 |
| B4 事件桥 | `common/LearningBridge.ets` | 阅读同步、章完成、流程阅读完成三个事件带身份作用域，时间线刷新 `/today`，对应流程刷新题目。 |

以上源码路径相对于 `entry/src/main/ets/`。

## 后端契约

- `chapter_range` 使用 `起点:长度`，段落和 `read_ranges` 使用全书 plain Unicode 码点的半开区间 `[start, end)`。章节接口可能返回跨章边界的完整段落，阅读器上报时会取与本章范围的交集。
- 阅读事实发送到 `POST /api/frontend/learning/reading-progress`；显式完成发送到 `POST /api/frontend/learning/chapter-complete`。
- 队列中 400/404 的失效记录会移出并记日志。409 的 `ProgressConflict` 表示会话 ID 被用于不同章节或不同开始时间，重发不能修复，也会移出。网络、5xx、限流及鉴权失败保留待重试。
- 同一作用域只有一个补发任务，多个心跳共用在途请求。ACK 只删除原作用域、原会话、原日中不新于已发送序号的记录。
- 队列保存结果与发送结果分开，历史坏记录被丢弃不会被误判成本次快照未保存。
- 问答使用 `POST /api/agent/v1/ask-in-context`，阅读遥测使用 `POST /api/telemetry/ingest`。
- 以当前后端为准：每日复习是 `/review-plan → /tasks/{id} → /review/submit`，保留 `quiz_id/attempt_id` 与生成时的章节来源；读后流程是 `/flow/state → /flow/submit`。两者都独立于普通题库。
- 服务卡片“好 / 晚点”的实际接口是 `POST /api/agent/v1/decision/respond`，请求包含 `decision_id/response`。

## 身份与异步状态

阅读器固定创建时的身份；账号或服务配置变化会立即停止计时并使旧内容请求失效。持久化队列按 `encodeURIComponent(serviceBase) + '|' + encodeURIComponent(username)` 隔离，重新登录同一作用域后可以补发以前的记录。

学习运行时配置带请求代次、用户名和主站地址校验，旧响应不能覆盖新账号或较新的配置。退出登录在等待网络注销前就撤销 Learning 身份。

卡片身份使用支持跨进程即时可见的 GSKV。切账号、切主站、禁用或更换学习服务时撤销旧卡片授权；卡片每次回写前再次校验主站会话，并核对当前卡片的身份与决策。

后端当前以服务器本地日聚合，尚未提供服务时区契约。离线队列同时保留设备自然日与 UTC 的边界，避免覆盖常见部署中的前一天快照；若需要任意服务器时区精确分日，需要后端明确时区。

## 验证

在 `NexoraApp` 目录执行（Node >= 22.13）：

```powershell
node --test tools/test_reader_coordinates.cjs tools/test_learning_reading.cjs tools/test_learning_reader.cjs tools/test_learning_agent.cjs tools/test_learning_system_entry.cjs tools/test_learning_runtime_races.cjs tools/test_learning_launch_retries.cjs
devecocli build
```

测试直接执行生产逻辑，使用可控时钟、HTTP 和存储替身，覆盖码点分页、前后台计时、跨章归属、持久化与 ACK 竞争、离线重试、切账号、旧请求、读后出题、重复深链与卡片回写。

设备联调需覆盖真实滑动分页、目录与问答面板、后台恢复、系统返回键、小艺意图和桌面卡片。当前工程没有签名配置，全量构建产物为未签名 HAP。

## 文档中的可选项

本次未包含选文工具栏、阅读实况窗和段落级本地续读位置。这些不影响以上数据闭环；阅读上报本身已包含 `paragraph_index/page_index`。

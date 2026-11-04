# 候选反馈统计与人工漏检线索 v0.2

日期：2026-10-26。

## 本轮范围

增加当前自有/竞品账号对的反馈概览，并允许从现有两篇作品选择器补录人工漏检线索。复用独立 event_feedback.db 和既有追加记录；不新增数据库表、列、索引或迁移，不修改采集、模型推断和候选排序。

开工只读核对：当前配置源库对应路径下 event_feedback.db 不存在，已保存反馈为0。没有代填此前口头判断。本轮只写合成隔离库的反馈，不写运行反馈库或采集库。

## 接口和口径

- 新增 GET `/api/monitor/event-comparison/feedback-summary`，参数 owned_account_id、competitor_account_id；前后校验账号身份与关联。显式点击读取，不轮询。
- 响应包括 as_of、total_pairs、counts、current_origins、scope。每对作品仅统计最大 revision；旧记录与新记录不重复计数。固定版本与当前材料不匹配归入 needs_review；隐藏、删除、当前不可访问作品归入 source_unavailable，两类不计入有效判断。
- counts 为 same_event、different_event、uncertain、needs_review、source_unavailable；总和为 total_pairs。current_origins 仅对当前绑定统计候选反馈/人工漏检线索，每对按最新记录来源分类，不是历史来源累计次数。
- 当前账号对超过500组拒绝，明确未截断，不输出部分统计。损坏存储不覆盖、不自动重建；GET不创建反馈库。
- 既有 POST feedback 新增可选 report_kind=candidate/manual_missed，默认candidate。普通请求哈希排除新增默认字段，保留旧请求幂等键重放；manual_missed参与哈希。旧payload缺字段按candidate解读，不批量修改旧记录。
- 人工漏检线索仅表明编辑报告，不证明配对真的未出现在某次候选结果；本期没有冻结检索快照。未计算准确率、召回率、热点预测命中率，不向70%指标作推断。
- 元数据读取快照与来源读取快照分离，不承诺跨数据库原子快照；统计截止不是平台实时发现时间。来源库整体不可用时报错，不把无法校验的全部记录算作有效。

## 界面

在现有同事件竞品对比中增加人工反馈概览，五个紧凑计数单元。无反馈如实显示空状态。显式保存后更新已打开的统计与同配对反馈记录。

选择两篇后显示“未被候选发现？”区域，显式展开补录；复用人工判断、备注、历史及409保留输入。不会自动勾选同事件，不触发分析模型，不创建事件分组。原来的候选反馈入口保留。

依据 ui-ux-pro-max 的表单异步错误建议处理状态，沿用项目主题色和边框，保留可聚焦按钮、可见标签、44像素操作高度和窄屏网格。

## 变更文件

1. api/services/event_feedback_service.py：统计、来源有效性检查、补录来源、旧哈希兼容。
2. api/routers/monitor.py：独立只读统计端点。
3. webui/src/lib/eventComparison.ts：类型、统计客户端和补录参数。
4. webui/src/components/monitor/EventCandidateFeedback.tsx：复用表单补录、保存后缓存失效。
5. webui/src/components/monitor/EventFeedbackSummary.tsx：新增统计组件。
6. webui/src/components/monitor/EventComparison.tsx：统计及手动补录入口。
7. tests/test_event_feedback.py：新增10项测试，包括旧格式请求哈希重放、最新计数、删除/更正文案/版本变化、空状态与无写入、角色、损坏库及上限。
8. tools/accept_event_comparison.py：注册真实统计路由，加入真实UI统计/补录/空状态/失效计数测试。
9. 本文档。

## 验证

- 选题无关的现有事件、账号、标题相关后端综合测试216项通过；新增反馈统计定向10项包含在内。之后增加损坏记录版本字段类型保护，定向反馈21项再跑通过。
- TypeScript：`npx tsc -b`通过。
- Vite：显式输出 `webui/dist-feedback-stats-20261026-01`，目录预先不存在；入口 index-DI3IVoSj.js，样式 index-qXv9iRVA.css。
- 共享 api/webui 路径集合及433个文件逐SHA一致。前后完整记录在 `tmp/feedback-stats-browser-20261026-02/shared-build-manifests.json`。
- 最终隔离浏览器23/23通过，`tmp/feedback-stats-browser-20261026-02/results.json`。包括显式统计空状态不建库、补录第5次历史记录、计数只计最新、并发保留输入、源变化后有效来源计数归零、三种宽度与深浅色。旧版对比与候选功能回归通过。
- 页面脚本错误0；页面外联尝试0。仅描述该隔离页面，不推断浏览器所有背景网络。
- 模型真实调用0；浏览器旧语义分析回归使用5次模型替身。合成样本时钟固定为2027年，不代表真实采集日期。所有写入发生在测试目录，测试服务已停止。
- 原SQLAlchemy、Browserslist和大包警告未处理。

## 应用与后续

独立构建尚未应用，不自动重启当前服务。先在采集空闲时重启后端加载新端点，再保全当前共享前端并切换独立构建；旧后端不支持report_kind，不应先切换新前端。

编辑显式保存真实判断，再查看统计和补录线索。后续需要建立明确评估集、检索快照和漏检核验流程，才能衡量召回；现有小样本判断不是质量承诺。

回滚仅恢复本轮具体源码/前端构建；保留反馈库与追加历史，不全局恢复工作区、不删除证据。v0.1反馈记录保留原值；回滚后的旧客户端可忽略新增payload字段，但本期尚未提供通用的全部历史/已删作品浏览器。

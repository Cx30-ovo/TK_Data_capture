# 话题监控删除功能

日期：2026-11-02。已本地应用独立构建 `webui/dist-topic-monitor-delete-20261102-01`。

话题详情操作区新增「删除监控」，点击后显示确认框与删除范围，默认聚焦取消。确认前不删除；取消或Esc关闭后返回触发按钮。删除成功显示结果，自动选择其他任务；没有任务时回到空状态。

新增 DELETE `/api/topic-monitors/{topic_id}?expected_version=N`，校验当前配置版本。版本变化返回409并保留任务，客户端不自动重试。删除在同事务移除该任务、专属轮次/观测及作品关联；仅清理该任务曾引用且已无其他引用的作品。其他话题共用作品及账号监控库不受删除操作影响。不新增表或迁移。

删除采集中任务时设置停止标记，当前请求返回后的未完成结果丢弃，释放共享锁，不恢复已删任务。处理了领取任务与注册停止标记之间被删除的竞态，在打开采集浏览器前重新检查任务存在。实际业务请求不因新增按钮自动发起删除。

修改文件：`database/topic_monitor_repository.py`、`api/services/topic_monitor_service.py`、`api/routers/topic_monitor.py`、`webui/src/lib/topicMonitor.ts`、`webui/src/components/monitor/TopicMonitor.tsx`、`tests/test_topic_monitor.py`、`tools/accept_topic_monitor.py`。

验证：

- 后端112项通过，覆盖删除外键顺序、共享作品保留、空任务删除、409/404/422、采集中删除及领取竞态、账号/话题共存和已有监控测试。
- 话题浏览器13/13通过，包含删除确认/取消、键盘焦点、375宽度深浅色、409不误删、删除后切换、最后任务空状态。
- 既有页面回归42/42通过；脚本错误0。隔离验收无真实平台或模型调用。
- TypeScript及Vite构建通过；既有主包体积提示仍存在。构建前后共享 `api/webui` 的1450文件路径和逐文件SHA一致。
- 随后独立应用41个构建资源并逐一核对服务返回SHA，完整旧构建备份保留在本轮证据目录。
- 正式任务未执行DELETE。现有1个真实任务完整保留，话题数据库字节SHA不变；账号矩阵及对比库SHA不变。原账号库恢复监控后有正常写入，不宣称全程不变。原监控及自动对比开关已恢复。

证据：`tmp/topic-monitor-delete-20261102-01/`、`tmp/topic-monitor-delete-browser-20261102-02/`、`tmp/topic-monitor-delete-regression-20261102-01/`。

删除无法从页面撤销，确认框明确告知；如只想暂时停止请使用「暂停话题」。

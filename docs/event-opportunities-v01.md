# 只读事件机会池 v0.1

已实现、验收并应用本地。入口：同事件竞品对比 → 事件机会池；默认仍是竞品对比，保留原页状态。机会卡可返回原分析；此动作只读取原任务，不重新调用模型。

## 首期边界

按一个已启用的自有账号与其一个关联竞品、3/7/14/30天窗口读取本地已采集作品和最近50批已有分析。不是全平台发现、完整账号覆盖审计、语义事件聚类、模型新推断、自动建稿或发布。目标账号来自当前有效账号关系，不硬编码。

三类线索：

- 覆盖待查：竞品作品未在当前窗口和所选账号组合命中字面候选，且未被有效已有同事件判断覆盖。显示“暂未检索到覆盖”，不称漏报、不宣称未报道；自有窗口作品可能为0，实际数量始终展示。
- 事实/角度差异：已有同事件模型推断中的 core_fact/angle/background；纯表达差异不纳入。只比较所选作品，材料是清理后发布文案级，不等于全文事实核验。
- 后续进展：已有模型标为 followup 的两篇作品；明确先后和事实仍需核实，不凭该分类宣称已确认的新进展。

事实差异 → 后续进展 → 角度差异 → 背景补充 → 覆盖待查，同级按竞品发布时间和稳定ID排序；可切换纯时间排序。规则带独立排名版本，不是热点概率、新闻价值分数或账号风格适配评分。

## 只读接口

GET /api/monitor/event-opportunities

必填 owned_account_id、competitor_account_id；可选 days（1—30，默认7）、kind（all/coverage_check/angle_gap/followup）、order（priority/recent）、page（每页10）。

返回版本、排序版本、材料截止、扫描数量、分类计数、当前分页、证据绑定、原任务ID、排除统计、已有分析读取范围和限制说明。来源不可用、身份无效、存储损坏或配对超限明确报错，不自动修复、建库或截断源检索。已有分析超过50批时显式提示范围不完整。

来源通过 query_only 事务只读；已有分析SQLite以mode=ro打开。GET不创建存储、不触发模型、图片下载、采集或后台任务。沿用现有候选的作品/总文案/72小时配对安全上限。

## 证据、去重与失效

使用同次候选检索快照中的当前作品身份和source SHA校验原分析；再次检查引用字段title、所属侧、作品ID、精确片段和片段SHA。缺失、删除、窗口外或绑定变化排除，不能提升为有效线索。

同一作品对只取读取范围内最新已完成分析，不回退到旧判断；同竞品作品、同类型及完全一致线索去重。不同作品对的不同依据保留，跨作品事件聚合后续再做，不能把同名主题强行合并。

机会池只用发布文案级依据；不以封面或快照当前状态推导机会。查看原分析保留原封面、互动和快照的既有失效提示。

## 源码及测试变更

新增：
- api/services/event_opportunity_service.py：只读聚合、引用复核、排序和范围说明。
- webui/src/lib/eventOpportunities.ts：类型及GET客户端。
- webui/src/components/monitor/EventOpportunityPool.tsx：筛选、卡片、原文依据、分页和错误/空状态。
- tests/test_event_opportunities.py：19个隔离定向测试。

修改：
- api/routers/monitor.py：追加只读GET路由。
- webui/src/components/monitor/EventComparisonPage.tsx：机会池视图入口，排除停用关系。
- webui/src/components/monitor/AutomaticComparison.tsx：接收原分析跳转上下文，只读打开已有任务。
- tools/accept_model_comparison.py：机会池浏览器验收。

没有新增表或迁移，没有改采集、匹配/分组、模型提示词、自动队列或预算规则。任务开发与验收不主动调用真实模型；切换后原有自动任务按原设置正常工作。

## 验证

后端254项通过（包括19项机会池定向测试与已有对比、自动队列、健康、图片/材料、候选和账号矩阵回归）。TypeScript及独立Vite构建通过；构建输出 webui/dist-event-opportunities-20261027-141635。

构建前后 api/webui 的965个相对路径与逐文件SHA无变化。应用前完整备份共享静态目录；先资源后index，不删除旧资源。应用后39个文件HTTP SHA逐一匹配。

浏览器最终34/34通过，页面脚本错误0；机会池覆盖只读SHA、原分析跳转、保守措辞、键盘展开、筛选空态、12条覆盖待查分页、排序重置、错误恢复以及1440/812/375深浅色布局。使用隔离数据库和模拟模型，未产生真实模型请求。首轮33/33证据保留，补充覆盖分页和错误恢复后34/34。

真实数据只读核对：近7天，自有148、竞品22篇；覆盖待查20、事实/角度差异0、后续进展0。26批已有分析读取完整，5对因窗口/绑定失效未纳入。实际GET前后采集库、已有分析库SHA相同。该数值为本次截点，后续采集会变化。

真实浏览器确认第一页1—10/20、第二页11—20/20，页面脚本错误0，未发起非GET请求。

## 证据

- tmp/event-opportunities-20261027-141635/build.log、build-result.json、static-before.json
- tmp/event-opportunities-20261027-141635/applied-files.json、live-verification.json
- tmp/event-opportunities-20261027-141635/real-readonly-preview.json
- tmp/event-opportunities-20261027-141635/webui-before/（共享前端完整保全）
- tmp/event-opportunities-20261027-141635/live-browser/results.json、opportunities-live.png
- tmp/event-opportunities-20261027-141635-browser-01/results.json（33/33）
- tmp/event-opportunities-20261027-141635-browser-02/results.json（34/34）
- tmp/event-opportunities-20261027-141635-browser-02/opportunities-1440-False.png 等六种布局截图

## 已知限制与下一步

机会卡以竞品作品为入口，不冒充模型生成的事件摘要；同事件跨作品语义聚类尚未实现。字面召回可能误配或漏检，所以覆盖待查不是覆盖缺口结论。规则排序不等于编辑价值评估，没有通过专用模型训练得到评分。已有分析最大50批，缺失分析时保持为空，不凑角度或新进展。GET需要本地有限计算；不自动频繁轮询，手动重读即可更新。

优先观察真实作品增量后机会池是否更新，并复核20条覆盖待查的噪声；下一阶段再决定跨作品聚合、选题卡与账号风格标题生成。不因机会池为空自动调用模型。

## 本地切换与回滚

重启前确认采集/调度和分析无在途工作，暂时暂停监控及自动开关；新版启动后原配置与暂停状态已恢复。恢复原前端可从本轮完整静态备份取回index及对应资源；源码按本轮文件修改逐项逆向，新增独立文件可解除接入。无需数据库回滚，不覆盖采集数据或旧分析。

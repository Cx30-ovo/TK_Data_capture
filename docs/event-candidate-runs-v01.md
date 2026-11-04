# 检索批次快照与漏检核验 v0.1

日期：2026-10-26（Asia/Shanghai）。已实施、隔离验收并按用户持续授权切换到本地运行版本。

## 行为

点击“查找候选”通过显式POST创建固定批次，保存账号对、时间窗口、截止时间、算法/标题提取/快照Schema版本、实际计算上限和字面规则、完整已扫描作品目录、来源SHA、输入SHA、完整有序候选配对及命中片段。相同作品只存一次，候选通过ID引用。分页从固定批次读取，不重新扫描采集库。

“历史检索批次”按账号对分页，只读打开旧批次。快照是当次读取的历史材料，不能当作当前材料；选入对比或保存判断仍校验当前来源。不会回算或覆盖旧批次。

补录可关联当前批次，也可取消关联只保存人工线索。关联时先显示只读核验预览，保存时服务端再次核验，结果和批次SHA追加到反馈历史。客户端不能提交核验结论。

五类结果：

| 状态 | 含义 |
|---|---|
| retrieved | 已在完整候选目录中，可能不在当前页，不属于漏检 |
| outside_batch | 至少一篇不在当次输入目录，不计为批次内漏检 |
| material_changed | 当前来源SHA与当次材料不同，不据此核验历史漏检 |
| outside_pair_gap | 两篇均在输入目录但超过该批次发布时间差上限，不计为漏检 |
| not_retrieved | 两篇材料一致且在配对范围内，当次完整结果未召回；是否同事件仍取决于人工判断 |

只有not_retrieved加人工same_event判断才形成“该人工判断配对在该批次内未召回”的依据，不代表平台事实核验。未关联记录不补写批次，不批量改旧记录。反馈统计继续按作品对最新判断计数，未新增准确率、召回率或热点预测命中率。

## 接口和存储

- POST `/api/monitor/event-comparison/candidate-runs`：owned_account_id、competitor_account_id、days、save_key。幂等键同参数重放原批次，不重新检索；不同参数409。
- GET 同路径：上述两个账号ID，page、page_size，返回历史目录。
- GET `/api/monitor/event-comparison/candidate-runs/{run_id}`：固定快照分页，包含run_id、snapshot_sha256、input_sha256、提取版本、frozen标记。原有候选响应字段保留。
- GET `/api/monitor/event-comparison/candidate-runs/{run_id}/check`：双方选择身份和SHA，校验当前材料后比对批次。
- POST既有feedback：可选candidate_run_id，服务端派生run_check。缺省时不进入请求哈希，保留v0.1/v0.2旧幂等规则；已有记录字节不批量更新。原有GET candidates保持只读、无持久化，供兼容客户端使用。

独立元数据为采集库同目录 `event_candidate_runs.db`，仅首次显式成功检索POST创建candidate_runs表；未加入全局自动建表。没有改采集库模型/表结构或执行迁移。SQLite自身为主键/唯一键生成索引，不新增采集库索引。API不提供覆盖或删除快照接口；这不是不可篡改存储，payload SHA用于内容一致性检查。

每批次最多沿用500篇/账号、20000配对和现有文案计算预算，快照编码最多8MiB，批次库最多1000个批次、256MiB预检上限；SQLite页分配与日志另有少量开销。超限明确拒绝，不截断、不清理旧资产、不降级为无快照检索。元数据路径禁止符号重定向或硬链接到采集库。损坏内容/哈希不匹配时拒绝，不重新计算冒充历史。

采集库读取、批次存储与反馈存储互相独立，不承诺跨库原子性：创建批次后关联角色可能变化，接口可失败而批次已保留；反馈保存后来源可能变化，既有独立事务限制仍适用。历史核验是保存时结果，页面明确标注，不冒充实时复核。

## 文件

- api/services/event_candidate_service.py：增加内部capture模式，复用同次读取/排序取得完整输入和有序结果，旧GET默认行为不变。
- api/services/event_candidate_run_service.py（新增）：独立元数据、幂等、容量限制、哈希、批次分页与五类核验。
- api/services/event_feedback_service.py：可选批次身份、旧哈希兼容、服务端核验记录及范围文案。
- api/routers/monitor.py：新增批次四端点，身份/关联校验和错误映射。
- webui/src/lib/eventComparison.ts：批次类型、客户端、可选保存字段。
- webui/src/components/monitor/EventCandidates.tsx：显式建批次、固定分页、历史目录。
- webui/src/components/monitor/EventCandidateFeedback.tsx：关联选择、核验预览、保存时核验历史、保留未提交输入。
- webui/src/components/monitor/EventComparison.tsx：按当前账号对传递批次上下文。
- tests/test_event_candidate_runs.py（新增）：24项定向用例。
- tests/test_event_feedback.py：旧请求夹具限定原始字段，避免新增可选字段改变历史样本。
- tools/accept_event_comparison.py：真实批次接口及隔离浏览器验收。
- 本文档。

界面沿用项目主题/组件；ui-ux-pro-max的异步错误建议用于保留错误与重试输入，添加原位状态、44像素按钮及可见标签，没有增加外部资源。

## 验证与应用

- 后端综合240项通过（含批次24项）。覆盖源库字节不变、GET不建库、首次独立建库、完整冻结分页、来源变化、五类结果、角色、幂等/并发、旧哈希、反伪造、内容破坏、容量和硬链接保护。
- TypeScript检查通过；独立Vite构建 `webui/dist-candidate-runs-20261026-01`，主资源index-4rdgU70E.js、样式index-DurDRD7E.css。构建前后共享api/webui的459个文件路径与逐SHA不变，完整记录在 `tmp/candidate-runs-browser-20261026-02/shared-build-manifests.json`。
- 最终隔离浏览器26/26通过：`tmp/candidate-runs-browser-20261026-02/results.json`。历史空状态GET不建库、固定快照删除后翻页、重开旧批次、已召回配对不能冒充漏检、范围内未召回人工补录、反馈/并发/原对比功能、三宽度深浅色和来源变化均通过；页面错误0、页面外联尝试0。此处不据此推断浏览器全部背景网络。
- 第一轮25/26：验收定位器因“共7组”同时命中摘要和范围而失败，已限定定位器；没有业务修补，完整第二轮通过，旧证据保留。
- 真实模型调用0；旧语义功能回归用模型替身5次。隔离合成样本时钟固定在2027年，不代表真实采集日期。
- 所有保存验证仅写隔离库。运行环境仅GET核对批次目录，当前0条；未代建真实批次或反馈，运行批次库仍不存在。
- 已切换新版：备份 `tmp/candidate-runs-apply-20261026-094446-91ad53/webui-before`，459个旧文件核验一致。无在途任务时安全暂停监控、重启本地后端，确认新接口/字段后资源先复制、index最后切换；36个新构建文件逐SHA核验一致，旧哈希资源保留。
- 在线入口、脚本、样式、favicon均正常；批次目录GET正常。监控paused=false、无在途任务，调度仍关闭，与更新前一致。应用检查不冒充另跑全套真实浏览器验收；正式采集可能持续正常写入，不宣称正式库全字节不变。
- SQLAlchemy、Browserslist和大包历史警告未处理。没有提交、推送或操作远程机器。

## 限制与下一步

没有可靠的历史批次可以回填升级前的漏检；批次仅覆盖已采集且符合当次过滤的作品，不能判断平台上未采到的作品。本文使用“范围外”而不猜测未入目录的具体原因。

尚未建立完整标注评估集或自动汇总召回率，历史目录也没有自动清理、导出与身份认证增强。容量达限时需另行确定保留/归档策略，不静默删除。下一步由编辑创建真实批次、保存判断并补录具体遗漏，积累可核验评估集后再调整检索规则。

回退采用本轮逐文件逆向补丁与已保全旧前端；不全局Git恢复，保留批次库与反馈历史，不删除旧证据。

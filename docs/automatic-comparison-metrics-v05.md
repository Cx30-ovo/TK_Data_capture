# 同期互动解读和原始计数展示修复 v0.5

## 本次核对

错误 `ec33fb1987ee` 的日志确认模型响应为成功状态，但 `interaction_analysis` 在 `section_evidence` 阶段被拒绝。截图对应存档的 24h 观测满足既有实际年龄容差规则：双方点赞 70/714、评论 6/99、收藏 4/83、分享 1/12。快照实际发布后年龄分别为 86,440 和 93,042 秒，差 6,602 秒，小于既有 8,640 秒容差。

因此“缺少双方同阶段快照”的固定提示不准确，不能用模型解读状态推断原始数据缺失。该次模型原始引用未保存，不能确定具体是哪条引用导致拒绝。完整核对登记在 `tmp/comparison-metrics-20261026-01/reported-material-audit.json`。

## 修改

- 前端根据存档原始材料区分“缺少可比数据”和“已有观测但模型未形成可校验解读”。有可比同期观测时直接展示四项原始计数、双方采集时间和发布后年龄；0 保留，缺失显示空缺标记。旧记录也可直接展示，不重新调用模型或覆盖原存档。
- 原校验器限制一个 finding 只引用一个指标，会拒绝同一阶段同时引用双方点赞、评论等多个指标的有效解读。现改为允许多个指标，每个指标仍须独立具备双方同阶段引用、满足实际年龄容差。不得用自有点赞与竞品评论交叉比较；不同阶段、单方、伪造和不可比材料仍拒绝。
- 增长解读同样允许相同区间的多指标引用，每项须具备双方证据且两端均可比，不放宽负增长与阶段区间校验。
- 服务端在模型输入增加 `comparison_options`，只列完整双边、可比的同指标及区间证据选择。新任务版本为 `automatic-competitor-analysis-v0.5`，不新增端点、请求参数、表或迁移。
- 子项失败日志增加受控原因代码，区分引用不存在、阶段不可比、指标缺少对侧、增长区间不同；不记录原始回答、地址或凭据。

源码为 `api/services/automatic_comparison_materials.py`、`api/services/automatic_comparison_service.py`、`webui/src/lib/automaticComparison.ts`、`webui/src/components/monitor/AutomaticComparison.tsx`；验证修改 `tests/test_automatic_comparison_materials.py` 和 `tools/accept_model_comparison.py`。

## 验证与应用

- 后端回归 195 项通过，包含多指标成对引用、缺少对侧仍拒绝、不可比选择排除以及模拟模型返回四指标引用的端到端测试。
- TypeScript、独立 Vite 构建通过：`webui/dist-comparison-metrics-20261026-01`。构建前后共享目录 708 个文件的路径和 SHA 不变。
- 隔离 Chrome 28/28 通过，新增八条引用的多指标解读、原始计数表、有数据不误报缺失测试；原有图片、单项降级、宽度/主题和键盘回归保持通过。页面脚本错误为 0。证据 `tmp/comparison-metrics-browser-20261026-01/results.json`。
- 当时 7 对真实候选只读预算预检通过；本轮真实模型调用和图片下载为 0，没有重放旧失败请求。
- 原构建保全于 `tmp/comparison-metrics-20261026-01/webui-before`。新产物先资源后入口应用，本地 HTTP 校验 39 个产物 SHA 一致。
- 确认无在途任务后暂停并重启本地后端、恢复原监控状态；旧任务 SHA 全部不变。见同目录 `live-check.json`。

现有截图所涉旧失败的模型解读仍保留失败状态；刷新后可以查看原始数据，新启动批次使用新规则。不能保证所有模型自然语言或引用都可通过，也不据此宣称互动因果或曝光归一化表现。

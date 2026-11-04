# 仅模型比对与后台页签焦点修复

2026-10-26，本地已应用。

## 变更

- `webui/src/components/monitor/EventComparisonPage.tsx`：移除人工 `EventComparison` 引用和挂载，仅保留模型模块，更新页面说明及空状态。
- `webui/src/components/monitor/AutomaticComparison.tsx`：模型不可用时不再宣称有人工对比入口，明确已有分析记录仍可查看。
- `api/services/monitor_service.py`：启动准备浏览器时不再调用 `page.bring_to_front()`。
- `media_platform/douyin/core.py`：启动缺少登录页签时复用已有 CDP 后台创建工具，避免 `context.new_page()` 选择新页签。保留现有登录、空页复用和采集页隔离规则。
- `tests/test_douyin_browser_startup.py`：后台建页和有头/无头均不激活页签的断言。
- `tools/accept_model_comparison.py`（新增）：模型专用页面与浏览器焦点隔离验收。

人工流程已从页面及运行构建中移除，不删除既有人工反馈数据或后端接口；原有历史测试工具保留作旧版证据，本轮不再用它验证已删除的界面。

## 跳转定位

前端 `tab=event-comparison&editorial=references&q=` 未发现指向抖音的自动 location 跳转。确认存在的抢前台路径为后台服务准备浏览器时主动 `bring_to_front()`，以及缺登录页签时 `new_page()` 前台创建。现已移除前者、替换后者。

这确认并修复项目可控的两个焦点触发点；不能把静态排查当作原用户现场每一次跳转均已归因。浏览器扩展、站点弹窗或操作系统窗口激活不在本次完全归因范围。完全退出后重新启动 Chrome 本身仍可能由操作系统激活新窗口；本轮验证已有登录浏览器的后台建页/复用。

## 验证与证据

- TypeScript 检查通过；Vite 独立输出 `webui/dist-model-only-20261026-01`，未改全局构建配置。
- 构建前后 `api/webui` 540 个旧文件的路径集合与逐文件 SHA 相同，清单 `tmp/model-only-20261026-01/shared-before.json`、`shared-after-build.json`。
- 相关后端 **141 项通过**：浏览器启动/采集后台页/恢复/自动分析 75 项；监控仓储、CDP、浏览器会话及无用户信息采集回归 66 项。没有把之前 268 项称为本轮重跑结果。
- 隔离 Chrome **20/20**，结果 `tmp/model-only-browser-20261026-01/results.json`。使用与用户相同的查询参数，所有操作后断言 URL 不变；人工区域、复选框及人工接口请求均不存在。覆盖键盘启动/展开、历史、非同事件、错误引用、停止、模型关闭、来源变更、空关系/错误、1440/812/375 深浅色。
- 使用真实隔离 Chrome/CDP 和真实后台页创建逻辑，启动准备重复两次、采集页创建与导航后，工作台 `visibilityState=visible`、`document.hasFocus()=true`，URL 不变。抖音导航由测试拦截器返回内存 HTML，没有访问平台；明确列为 mocked_platform_navigation_paths，不伪称实际平台采集验收。
- 页面脚本错误 0，测试监听范围内意外外部页面请求 0；真实模型调用 0，模拟模型响应 4 次。未把该页面监听结论扩大到 Chrome 背景网络。
- 本地开发前端只读请求确认模型专用组件已生效；构建页面 38 个文件通过既有路由逐 SHA 核验，详见 `tmp/model-only-20261026-01/live-check.json`。

## 应用与回退

验收后保全 540 个旧构建文件到 `tmp/model-only-20261026-01/webui-before`，资源先复制、index 最后切换，共应用 38 文件，旧哈希资源保留。清单为 `applied-files.json`。构建阶段共享目录零变化，后续授权应用阶段明确有变化。

确认无在途采集、无活动模型批次，安全暂停监控，核对本项目父子进程后重启后端；恢复原监控未暂停状态，调度仍关闭。未代启动真实模型分析、未改采集频率/风控冷却、未操作远程机器、未提交推送。

回退仅恢复本轮具体文件和保全构建后重启本地服务，不全局 Git 恢复、不删除历史反馈/分析或采集数据。

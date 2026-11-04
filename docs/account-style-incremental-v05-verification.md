# 增量账号档案实现与验证

## 变更

- api/services/account_style_service.py：v0.5；逐篇材料身份、批次缓存复用、待分析队列、30篇/24小时提示、30天原文重新校准、预算前检、输入变化拒绝保存。
- api/routers/monitor.py：传递可选请求预算，现有端点不变。
- webui/src/lib/accountStyle.ts：增量状态类型、POST预算。
- webui/src/components/monitor/AccountStyleProfile.tsx：近期/长期切换、预算选择、待分析与复用计数。
- tests/test_account_style.py：新增9项增量验证，保留原测试。
- tools/accept_account_style.py：预算/窗口切换验收，转发预算，适配真实失败批次变化。
- docs/account-style-incremental-v05.md：范围、失效策略、限制。

## 结果

- 后端相关测试93通过，包含33项风格分析测试。仅使用隔离库与模拟模型。
- TypeScript通过；Vite独立构建通过。
- 构建目录：webui/dist-style-incremental-20261023-01。
- 主资源：index-C12N43vV.js。
- 构建前后 api/webui 355个文件路径与逐文件SHA全部一致。
- 风格浏览器16/16：tmp/style-incremental-browser-20261023-01/results.json。
- 矩阵浏览器16/16：tmp/style-incremental-matrix-20261023-01/results.json。
- 两轮浏览器均无页面脚本错误、未捕获页面外部请求；真实模型调用0。
- 覆盖1440/812/375深浅色；查看了375深色截图。
- Vite原有大包/Browserslist提醒仍在，不影响构建通过。

## 当前运行状态与限制

代码和独立构建已完成。检查时本地运行服务仍报告v0.4；本轮未重启正在运行的监控服务，未将构建复制至api/webui。
因此不能声称线上/本地运行页面已更新为v0.5。
本轮不执行真实模型推断，不生成正式新档案；后续由编辑主动更新。
逐篇校验、批次级语义复用，尚非独立逐篇风格模型分析。抽样变化可能带来多个批次重算。
待分析队列是可重建派生数据，不是新增持久任务系统。没有自动模型执行开关或后台调度；自动执行保持关闭。
长期365天与近期独立，均最多500篇；不宣称覆盖全部历史。
没有数据库迁移，没有修改采集/快照调度逻辑，没有提交或推送。

## 下一步

确认本地无在途采集后切换独立构建并重启本地后端，验证v0.5 GET状态，再由编辑显式更新一次档案。
如需自动模型更新，后续增加独立授权开关、每日预算及持久任务执行机制，不通过页面GET触发。

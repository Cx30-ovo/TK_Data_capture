# 移除综合分析详细依据展示

按截图要求移除封面内容、同期互动、快照变化中的“查看…依据”入口及其完整展开内容，删除不再使用的字段名称映射。状态标签简化为“模型解读”。保留分析结论、计数图表、观测时间入口、材料变化和单项校验失败提示；文案原文依据入口及后端证据校验不变。不删除存档或修改接口。

修改源码 `webui/src/components/monitor/AutomaticComparison.tsx`，调整浏览器验收 `tools/accept_model_comparison.py`：验证详细依据控件与材料绑定展示不存在、分析结果和真实 0/缺失仍正确、单项异常不丢弃其他结果。原后端验证不放宽。

TypeScript/Vite 通过，独立构建 `webui/dist-comparison-clean-evidence-20261027-01`。构建前后共享目录 851 个文件路径及 SHA 一致。隔离浏览器 30/30 通过，脚本错误 0；结果 `tmp/comparison-clean-evidence-browser-20261027-01/results.json`，三种宽度及深浅色截图保留。全部使用模拟模型/图片与隔离库，真实模型调用 0。

本地前端已更新，39 个产物 HTTP SHA 一致。原产物备份 `tmp/comparison-clean-evidence-20261027-01/webui-before`，旧哈希资源保留，未重启后端或变更后台任务。回滚恢复本轮备份入口及资源即可，无需全局恢复。

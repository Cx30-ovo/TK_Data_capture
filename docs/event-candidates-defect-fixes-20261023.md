# 候选发现两项缺陷修复

2026-10-23。

## 变更

- `api/services/title_sentence.py`：署名识别增加“见习”前缀及中间空格，清理起始括号，不改写原始文案；提取版本升级为 `caption-cleaned-title-v4`，旧绑定失效。
- `tests/test_title_sentence.py`：增加真实泽连斯基样本、中文/英文括号、全角分隔符、换行空格及非署名正文的回归。
- `webui/index.html`：favicon由不存在根路径 `/vite.svg` 改为已有静态路由 `/logos/my_logo.png`。

## 验证与应用

- 后端167项通过，覆盖提取、候选、对比、档案、风格和标题统计。
- TypeScript、Vite独立构建通过：`webui/dist-event-candidates-fixes-20261023-01`。
- 隔离浏览器19/19：`tmp/event-candidates-fixes-browser-20261023-01/results.json`，页面脚本异常0。
- 真实作品只读核对提取后为“泽连斯基：愿在保留至少75%领土控制权的基础上达成和平协议。”，27字，无“（见习”残留。
- 前端只变更index.html；备份至 `tmp/event-candidates-defect-fixes-20261023-01/index-before.html`，应用前后备份/来源SHA核对通过，旧资源保留。
- 运行首页与新构建字节一致，图标实际GET返回200、image/png。前端修复已生效。
- 当前后端进程尚未重载，真实候选GET仍返回旧署名残留；不能将源码修复写成运行后端已生效。未自动暂停监控或重启服务。下次重启后刷新候选、重新选入配对以获取v4来源绑定。
- 本轮真实模型调用0，无迁移或正式库写入，无提交推送、远程机器操作。旧账号档案不批量改写。

回滚采用本次源码定向逆向补丁，前端恢复备份index.html；不全局恢复工作区。既有SQLAlchemy弃用、Browserslist及包体积提示未处理。

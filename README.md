# TK Data Capture

抖音账号持续监控、作品互动快照与分析导出工具。

本项目是在开源项目 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) 的基础上进行二次修改和功能扩展的版本，仓库地址为 [Cx30-ovo/TK_Data_capture](https://github.com/Cx30-ovo/TK_Data_capture)。

本项目不是 MediaCrawler 官方项目，也不代表原作者。原始项目的浏览器自动化、媒体平台采集和基础 WebUI 能力来自 MediaCrawler；本仓库主要围绕抖音账号持续监控、互动生命周期快照、任务告警、AI 研报、数据分析和报告导出进行了扩展。

## 项目定位

上游 MediaCrawler 更偏向一次性执行的关键词搜索、作品详情和创作者主页采集。本仓库在其基础上增加了持续监控能力，主要用于跟踪指定抖音账号的更新情况，并记录作品发布后的互动变化。

典型使用场景：

- 监控多个抖音账号，定期发现新发布的作品。
- 保存作品标题、正文、发布时间、作品 ID 和规范 URL。
- 在作品发布后的 1h、6h、24h、72h 和 7d 采集互动快照。
- 区分真实观测时间、计划时间和实际发布后年龄。
- 查看点赞、收藏、评论、分享的变化趋势。
- 对异常任务进行重试、分类和告警处理。
- 使用云端或本地 OpenAI 兼容模型生成主题和生命周期 AI 研报。
- 导出作品列表、快照历史和日报、周报、月报。
- 通过 WebUI 查看账号表现、作品排行、主题标签和生命周期分析。

当前 WebUI 和持续监控能力以抖音为主。上游代码中仍保留了其他平台的采集实现，但本仓库没有对所有平台逐项验证，README 不将其作为当前版本的稳定功能承诺。

## 主要功能

### 1. 抖音多账号监控

- 支持新增、编辑、启用、停用和删除多个监控账号。
- 监控账号必须使用抖音用户主页 URL 或 `sec_user_id`。
- 支持为不同账号设置发现间隔。
- 支持选择单个账号或全部账号查看监控数据。
- 删除监控账号时保留已经采集的数据。
- 支持修改账号显示名称，便于在 WebUI 中识别。

### 2. 增量发现新作品

- 后台根据账号的发现间隔检查新作品。
- 已存在的作品不会重复插入。
- 发现新作品后保存作品基础信息和规范作品 URL。
- 第一次发现作品时保存 `first_seen` 快照。
- 不保证自动回填监控开始前的全部历史作品。

### 3. 互动生命周期快照

每个新作品默认生成以下快照任务：

| 阶段 | 计划时间 | 允许执行窗口 |
| --- | --- | --- |
| `1h` | 发布后 1 小时 | 30 分钟 |
| `6h` | 发布后 6 小时 | 2 小时 |
| `24h` | 发布后 24 小时 | 6 小时 |
| `72h` | 发布后 72 小时 | 12 小时 |
| `7d` | 发布后 7 天 | 24 小时 |

每个快照记录：

- 计划采集时间 `due_at`。
- 实际观测时间 `captured_at`。
- 实际发布后年龄 `actual_age_seconds`。
- 点赞、收藏、评论和分享数量。
- 任务状态、失败原因和错过原因。

系统不会用后来的累计互动值倒填已经错过的历史阶段。超出允许窗口后，任务会标记为 `missed`，这是预期行为。

### 4. 任务与告警

- 任务中心支持查看待执行、执行中、已完成、失败和错过任务。
- 支持按作品、状态和类型搜索任务。
- 支持查看失败原因、错过原因、尝试次数和原始错误。
- 支持单任务重试和失败任务批量重试。
- 告警按问题合并展示，支持未读、已读、已解决和已忽略状态。
- 系统健康页显示数据库、浏览器、采集循环、磁盘空间和备份状态。

### 5. 数据分析

WebUI 的“监控数据”页面包含以下分析模块：

- 作品效果总览和核心指标。
- 点赞榜、分享榜和评论榜同时展示的 TOP10 榜单。
- 点赞与评论四象限图。
- AI 主题与标签研报。
- AI 生命周期研报。
- 生命周期节奏分布。
- 作品快照节点和 AI 生命周期诊断。
- 点赞率、收藏率、评论率和分享率。
- 发布时段热力图。
- 异常爆发增长检测。

### 6. AI 智能分析

- 支持 OpenAI 兼容的云端模型，例如 Qwen。
- 支持 Ollama、vLLM、LM Studio 和 LiteLLM 等兼容接口。
- 主题分析生成核心总结、主题洞察、核心标签、代表作特征和行动建议。
- 生命周期分析生成阶段观察、传播节奏分布和作品级 AI 诊断。
- 模型只负责归纳和解释，互动数字、阶段增量和节奏类型仍由后端计算。
- 分析结果写入 `ai_analysis_results` 缓存表。
- 相同账号、数据和提示词版本优先读取缓存。
- 支持“重新生成”强制刷新。
- 模型输出异常、上下文超限或超时时返回结构化错误。

### 7. 导出与报告

- 导出作品列表为 CSV 或 Excel。
- 搜索并多选作品后导出完整快照历史。
- 生成日报、周报和月报。
- 查看报告生成时间、时间范围、文件大小和状态。
- 下载或删除已生成的报告。

### 8. 浏览器复用与风控重试

- 默认使用 CDP 模式连接 Chrome 或 Edge。
- 优先复用同一个浏览器进程和稳定标签页。
- 记录 CDP 端口，连接失效时自动扫描可用端口。
- 采集遇到风控时可等待后重试。
- 默认等待 600 秒，相关配置位于 `config/base_config.py`。
- 浏览器和平台登录状态失效时，需要在浏览器中重新登录。

### 9. 自动维护

- 支持 SQLite 自动备份。
- 支持日志轮转和过期清理。
- 支持后端异常退出后自动重启。
- 提供 Windows PowerShell 启动脚本。
- 提供 Windows 任务计划安装和卸载脚本。

## WebUI 页面

当前 WebUI 包含五个主要页签：

| 页签 | 功能 |
| --- | --- |
| 概览 | 今日新增、异常任务、下次发现、下次快照、最近事件和待处理问题 |
| 监控数据 | 作品效果、三个 TOP10 榜单、AI 主题研报和 AI 生命周期研报 |
| 任务与告警 | 任务队列、失败重试、告警和系统健康 |
| 导出报告 | 作品与快照导出、日报/周报/月报 |
| 采集配置 | 多账号监控、采集范围、运行策略和系统维护 |

页面底部保留全局系统控制台抽屉，用于查看后端、调度器和监控循环日志。

## 技术栈

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy
- SQLite
- Playwright / Chrome DevTools Protocol
- React 18
- TypeScript
- Vite
- Tailwind CSS
- Radix UI
- TanStack Query
- Zustand
- OpenAI 兼容模型接口
- Qwen / LiteLLM / Ollama / vLLM

## 环境要求

- Windows 10 或 Windows 11，推荐使用 Windows PowerShell。
- Python 3.11 或更高版本。
- Node.js 18 或更高版本。
- npm。
- Chrome 或 Edge。
- `uv`，推荐用于创建 Python 环境和同步依赖。

如果 PowerShell 禁止运行 `npm.ps1`，请使用 `npm.cmd`，或通过 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 调整当前用户的脚本策略。

## 安装

### 1. 获取代码

```powershell
git clone https://github.com/Cx30-ovo/TK_Data_capture.git
cd TK_Data_capture
```

如果源码位于其他目录，后续命令请替换为实际项目路径。

### 2. 安装 Python 依赖

在项目根目录执行：

```powershell
uv sync
```

`uv sync` 会创建或同步项目虚拟环境。默认情况下，Windows 虚拟环境位于：

```text
.venv\Scripts\python.exe
```

如果使用已经存在的虚拟环境，也可以执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. 安装前端依赖

```powershell
cd webui
npm.cmd install
cd ..
```

### 4. 构建生产版 WebUI

```powershell
cd webui
npm.cmd run build
cd ..
```

构建产物输出到 `api/webui/`。构建完成后，后端可以直接提供 WebUI 静态资源。

### 5. 可选：配置 AI 分析

复制环境变量模板：

```powershell
Copy-Item .env.example .env
```

编辑项目根目录的 `.env`：

```env
AI_ENABLED=true
AI_PROVIDER=openai_compatible
AI_BASE_URL=http://192.168.101.244:4000/v1
AI_API_KEY=你的本地APIKey
AI_MODEL=Qwen3.8-27B-FP8
AI_TIMEOUT_SECONDS=300
AI_MAX_TOKENS=8192
AI_TEMPERATURE=0.2
AI_MAX_RETRIES=2
AI_ANALYSIS_CACHE_TTL_HOURS=24
```

说明：

- `.env` 已被 Git 忽略，不要提交 API Key。
- `AI_BASE_URL` 必须包含兼容接口的 `/v1` 路径。
- 修改 `.env` 后需要重启后端。
- 本地模型不需要 API Key 时可以将 `AI_API_KEY` 留空。
- 首次 AI 分析通常需要 30 到 120 秒，生成后写入缓存，再次打开可快速读取。

## 启动

### 方式一：开发模式

开发模式需要同时启动后端和 Vite 前端服务器。

终端 1，启动后端：

```powershell
cd D:\Project\MediaCrawler-main
uv run uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload
```

终端 2，启动前端：

```powershell
cd D:\Project\MediaCrawler-main\webui
npm.cmd run dev
```

浏览器访问：

```text
http://localhost:5173/
```

Vite 会把 `/api` 请求代理到 `http://localhost:8080`。

### 方式二：生产模式

先完成前端构建，然后只启动后端：

```powershell
cd D:\Project\MediaCrawler-main
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8080
```

浏览器访问：

```text
http://127.0.0.1:8080/
```

FastAPI 接口文档：

```text
http://127.0.0.1:8080/docs
```

独立日报页面：

```text
http://127.0.0.1:8080/daily.html
```

### 方式三：Windows 一键启动

项目根目录提供：

```text
start_mediacrawler.bat
```

双击后会启动：

- 带自动重启的后端进程。
- WebUI 开发服务器。

使用前需要先完成 Python 依赖和前端依赖安装，并确保 `.venv\Scripts\python.exe` 存在。

## 使用流程

1. 启动后端服务。
2. 等待项目专用浏览器启动，并完成抖音登录。
3. 打开 WebUI，进入“采集配置”。
4. 点击“新增账号”，填写账号显示名称和抖音主页 URL 或 `sec_user_id`。
5. 设置发现间隔，启用监控并保存配置。
6. 可点击“立即发现”验证账号和登录状态。
7. 进入“概览”和“监控数据”查看作品、任务和快照结果。
8. 在“主题 / 标签分析”和“生命周期分析”中生成 AI 研报。
9. 进入“任务与告警”处理失败任务和系统告警。
10. 进入“导出报告”导出数据或生成周期报告。

监控任务依赖后端服务持续运行。关闭后端后，到期快照和定时发现不会继续执行。

## 浏览器和 CDP 配置

主要配置位于 `config/base_config.py`：

```python
ENABLE_CDP_MODE = True
CDP_DEBUG_PORT = 9222
START_BROWSER_ON_SERVICE_START = True
AUTO_CLOSE_BROWSER = False
```

相关说明：

- `ENABLE_CDP_MODE=True` 时使用真实 Chrome 或 Edge 环境。
- 后端启动时可以自动准备项目专用浏览器。
- 浏览器数据默认保存在 `browser_data/`，该目录不提交到 Git。
- 项目会优先复用已经存在且有效的 CDP 端口。
- 如果浏览器连接失败，检查端口占用、浏览器登录状态和远程调试权限。

使用外部已启动的浏览器时，需要确保浏览器启用了远程调试，并监听配置的 CDP 端口。

## 风控重试配置

```python
ENABLE_RISK_CONTROL_RETRY = True
RISK_CONTROL_RETRY_DELAY_SECONDS = 600
```

默认行为是在遇到风控后等待 600 秒再重试。重试仍然受到任务允许窗口和最大尝试次数限制。系统不会通过延迟重试伪造历史快照。

## 数据存储

### SQLite 数据库

监控模块默认使用：

```text
database/sqlite_tables.db
```

主要数据表：

| 表名 | 用途 |
| --- | --- |
| `douyin_monitored_accounts` | 监控账号、显示名称、间隔和最近发现时间 |
| `douyin_posts` | 作品基础信息、发布时间和首次发现时间 |
| `douyin_post_snapshots` | `first_seen` 及 1h、6h、24h、72h、7d 快照 |
| `douyin_monitor_jobs` | 发现、快照和选题任务队列 |
| `douyin_topic_profiles` | 周期选题分析结果 |
| `monitor_alerts` | 系统告警、严重级别和处理状态 |
| `ai_analysis_results` | AI 主题和生命周期分析结果及缓存 |

数据库初始化由后端启动流程自动完成。升级已有数据时，项目会执行必要的表结构迁移。

### 运行文件

| 路径 | 内容 |
| --- | --- |
| `output/crawler.log` | Python 爬虫日志 |
| `output/webui.log` | WebUI、调度器和监控循环日志 |
| `output/exports/` | CSV 和 Excel 导出文件 |
| `output/reports/` | 日报、周报和月报 |
| `output/backups/` | SQLite 自动备份 |
| `data/` | 上游采集器生成的原始数据 |
| `browser_data/` | 项目专用浏览器用户数据 |

上述运行目录中的日志、数据库备份、导出文件和浏览器数据通常不会提交到 Git。

## AI 分析配置

AI 分析配置位于项目根目录 `.env`，由后端启动时自动加载。前端不会直接接触 API Key。

推荐配置：

```env
AI_ENABLED=true
AI_PROVIDER=openai_compatible
AI_BASE_URL=http://192.168.101.244:4000/v1
AI_API_KEY=
AI_MODEL=Qwen3.8-27B-FP8
AI_TIMEOUT_SECONDS=300
AI_MAX_TOKENS=8192
AI_TEMPERATURE=0.2
AI_MAX_RETRIES=2
AI_ANALYSIS_CACHE_TTL_HOURS=24
```

当前 WebUI 默认使用：

- 主题分析：最多 10 篇文章作为模型分析样本。
- 生命周期分析：最多 6 篇带生命周期快照的作品。
- 后端仍保留更大的分析上限，但为了避免模型上下文超限和长时间等待，界面默认使用较小样本。

AI 研报的互动数字和生命周期类型由后端重新计算，模型只负责聚类、总结、诊断和建议。

## 常用配置

在 `config/base_config.py` 中可以调整：

```python
PLATFORM = "dy"
CRAWLER_TYPE = "creator"
START_TIME = ""
END_TIME = ""
CRAWLER_MAX_NOTES_COUNT = 15
ENABLE_GET_COMMENTS = True
ENABLE_GET_SUB_COMMENTS = False
SAVE_DATA_OPTION = "jsonl"
```

说明：

- `START_TIME` 和 `END_TIME` 用于抖音作品发布时间区间筛选。
- `CRAWLER_MAX_NOTES_COUNT` 控制单次任务最多处理的作品数量。
- `ENABLE_GET_COMMENTS` 控制是否采集评论。
- `ENABLE_GET_SUB_COMMENTS` 控制是否采集二级评论。
- `SAVE_DATA_OPTION` 控制上游一次性采集任务的数据保存方式。
- 多账号持续监控的数据统一写入监控 SQLite 表，不受 `SAVE_DATA_OPTION` 直接控制。

## 主要 API

启动后端后可访问 `/docs` 查看完整接口。常用接口如下：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 后端健康检查 |
| POST | `/api/crawler/start` | 启动一次性爬虫任务 |
| POST | `/api/crawler/stop` | 停止当前爬虫任务 |
| GET | `/api/crawler/status` | 查询爬虫状态 |
| GET | `/api/monitor/accounts` | 查询监控账号 |
| POST | `/api/monitor/accounts` | 新增监控账号 |
| PUT | `/api/monitor/accounts/{account_id}` | 修改监控账号 |
| DELETE | `/api/monitor/accounts/{account_id}` | 删除监控账号 |
| POST | `/api/monitor/accounts/{account_id}/discover` | 立即发现指定账号的新作品 |
| GET | `/api/monitor/overview` | 查询概览数据 |
| GET | `/api/monitor/jobs` | 查询任务列表 |
| GET | `/api/monitor/alerts` | 查询告警 |
| GET | `/api/monitor/health` | 查询系统健康状态 |
| GET | `/api/monitor/analytics` | 查询分析数据 |
| GET | `/api/monitor/ai/status` | 查询模型配置和连接状态 |
| POST | `/api/monitor/ai/analyze/topics` | 生成或刷新主题 AI 研报 |
| POST | `/api/monitor/ai/analyze/lifecycle` | 生成或刷新生命周期 AI 研报 |
| GET | `/api/monitor/ai/results` | 查询 AI 分析历史 |
| GET | `/api/monitor/ai/results/{result_id}` | 查询单条 AI 分析结果 |
| DELETE | `/api/monitor/ai/results/{result_id}` | 删除 AI 分析结果 |
| GET | `/api/monitor/export/posts` | 导出作品列表 |
| GET | `/api/monitor/export/snapshots` | 导出快照历史 |
| POST | `/api/monitor/reports/generate` | 生成周期报告 |

## Windows 任务计划

项目提供以下脚本：

```text
install_windows_task.bat
uninstall_windows_task.bat
```

安装任务计划：

```powershell
.\install_windows_task.bat
```

脚本会创建名为 `MediaCrawlerBackend` 的计划任务，在用户登录时启动后端，并在进程异常退出后尝试重启。

卸载任务计划：

```powershell
.\uninstall_windows_task.bat
```

任务计划只负责启动后端。WebUI 开发服务器通常不需要安装为计划任务；生产使用时应先将 WebUI 构建到 `api/webui/`，再由后端提供服务。

## 测试

运行监控模块测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest tests\test_monitor_repository.py -q -p no:cacheprovider --basetemp=output\pytest-tmp
```

验证前端 TypeScript 和生产构建：

```powershell
cd webui
npm.cmd run build
```

当前监控模块测试覆盖账号隔离、作品去重、快照任务、错过窗口、失败重试、导出报告、分析指标和自动维护等主要流程。

运行 AI 模型、路由、缓存和分析编排测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -m pytest tests\test_ai_model_service.py tests\test_ai_analysis_repository.py tests\test_ai_analysis_service.py tests\test_ai_router.py -q -p no:cacheprovider --basetemp=output\pytest-ai
```

当前 AI 测试覆盖模型列表、JSON 输出解析、缓存读写、主题指标重算、生命周期兜底、API 路由和错误映射。

## 目录结构

```text
.
|-- api/                    FastAPI 服务、路由、服务和模型
|-- config/                 爬虫和系统配置
|-- database/               SQLAlchemy 模型、会话和仓储
|-- docs/                   项目文档
|-- media_platform/         各平台采集实现
|-- output/                 日志、导出、报告和数据库备份
|-- scripts/                Windows 启动和维护脚本
|-- tests/                  Python 测试
|-- tools/                  CDP 浏览器和通用工具
|-- webui/                  React WebUI 源码
|-- main.py                 上游命令行采集入口
`-- start_mediacrawler.bat  Windows 一键启动入口
```

## 已知限制

- 持续监控主要针对抖音，其他平台来自上游代码，当前 WebUI 未完整保留其全部操作入口。
- 监控开始前已经错过的阶段不会自动倒填，符合预期的数据会保持为 `missed`。
- 后端服务停止时不会执行发现和快照任务。
- 首次发现的互动值不等于 1h 快照，系统会分别保存 `first_seen` 和计划阶段。
- 账号登录失效后需要重新登录，程序不会绕过验证码或平台安全机制。
- 大幅修改数据库结构或清理 `browser_data/` 前，应先备份数据库和登录状态。
- 日报、周报和月报是本地 Markdown 报告，不是在线协作文档。
- 首次 AI 分析依赖模型推理速度，通常需要 30 到 120 秒；相同数据再次打开优先读取缓存。
- AI 主题和生命周期结果受样本数量及快照完整度影响，数据不足时会显示边界提示。
- AI 分析仅支持单个账号，不能直接对“全部账号”执行。
- 模型接口必须兼容 OpenAI Chat Completions，并支持 JSON 输出。

## 安全与合规

本项目仅用于个人学习、研究和合规的数据分析。

使用时必须遵守：

- 目标平台的服务条款和 robots 规则。
- 适用的法律法规和隐私要求。
- 合理控制请求频率。
- 不进行大规模抓取、批量骚扰、账号操纵或非法传播。
- 不采集、传播或滥用敏感个人信息。
- 不使用本项目绕过登录、验证码、访问控制或其他安全机制。

使用者应自行承担因部署、运行、采集、存储和使用数据产生的责任。

## 来源、致谢与许可证

本项目的上游项目为：

- [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)
- 上游文档：[https://nanmicoder.github.io/MediaCrawler/](https://nanmicoder.github.io/MediaCrawler/)

本仓库是在上游代码基础上进行的二次修改，主要新增和调整了抖音多账号监控、互动快照、任务队列、告警、系统健康、Qwen AI 研报、分析可视化和报告导出等功能。

感谢 MediaCrawler 原作者 NanmiCoder 及所有贡献者提供基础的浏览器自动化和平台采集实现。

本仓库继续遵循根目录 [LICENSE](LICENSE) 中的许可证要求。上游项目声明为非商业学习许可，使用前请完整阅读许可证，不要将本项目用于商业用途或其他违反许可证和相关法律的场景。

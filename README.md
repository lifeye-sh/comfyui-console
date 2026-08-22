# ComfyUI Console

ComfyUI Console 是一个面向本地或远程 ComfyUI 节点的统一 AI 内容生成管理平台，提供配置驱动的图片、视频和音频生成，工作流管理、参数映射、批量任务、独立调度、素材归档以及桌面端和移动端访问能力。

项目地址：[https://github.com/lifeye-sh/comfyui-console](https://github.com/lifeye-sh/comfyui-console)

当前仓库同时包含 V1 稳定界面和 V2 Glassmorphism 新界面。V2 使用独立的 `/v2` 路由和构建时功能开关，复用同一套认证、任务、素材和工作流数据；关闭 V2 后仍可立即回到 V1，不影响历史任务和数据。

## 当前版本状态

- V1 保留为稳定回退版本，原有路由和核心功能继续可用。
- V2 已完成八轮主要迭代，具备系统概览、统一生成、任务管理、批次任务、素材中心、工作流中心和系统配置页面。
- V2.1 已建立 AI 短剧工作台，当前支持小说导入、结构化分析、故事档案确认、AI 改编方案、世界设定、分镜和镜头生产闭环。
- V2 生成类型配置支持草稿、发布版本、参数设计、工作流 JSON 导入与节点映射，并记录任务使用的配置版本。
- 后端调度器在独立线程运行，登录和普通 API 请求不会被排队任务阻塞；管理员可在 V2”运行监控”查看心跳、节点与在途任务。
- V2 默认仍由构建变量控制，部署时可选择只发布 V1、开放 V2，或按比例灰度开放。

当前质量基线：后端 `101` 项测试通过，前端 `vue-tsc --noEmit` 与 Vite 生产构建通过（2026-08-22）。

## 主要功能

- V1/V2 双界面、独立路由、构建开关与回退机制。
- 图片、视频和音频生成类型动态菜单，V2 按媒体类别分组。
- 文生图、图生图、文生视频、图生视频、动作迁移等生成页面。
- ComfyUI API JSON 工作流导入、版本管理、参数自动匹配、节点属性选择和手工映射。
- 生成类型配置草稿、不可变发布版本、回滚基础能力和工作流绑定完整度检查。
- 每种生成类型只显示和管理本类型工作流。
- 批量任务行、逐行生成、批量生成、复制和提示词文件导入。
- 图片、视频和音频输入支持上传或从素材库选择，并提供预览。
- 任务管理、当天过滤、批量操作、任务详情、执行事件、结果预览、删除和重新生成。
- 在任务详情修改参数，并创建一条新任务执行，不改变原任务。
- 素材库无限级目录、任务结果按月/日期自动归档、多媒体预览、下载和生成参数查看。
- 图片预览支持缩放和拖动；视频显示首帧并可播放；音频支持在线播放。
- ComfyUI 多节点管理、独立线程调度、并发控制、失败重试、异常恢复和结果自动回收。
- 提示词库、参数方案、尺寸选项、审计日志、分享和回收站。
- 管理员运行监控、调度器心跳、节点探测和异常任务释放/重提。
- 响应式 Web 页面，支持桌面浏览器和移动端访问。
- OpenAI 兼容模型配置、加密密钥保存、连接测试、小说分块分析、JSON 自动修复和调用用量审计。
- 单集 AI 剧本候选、分集锁定、人工确认应用和自动版本快照，AI 生成不会直接覆盖人工草稿。

### 新增功能（2026-08-22）

- 生成任务行置顶：V1 与 V2 的全部生成页面点击“新增任务行”后，新任务会插入列表顶部，便于立即编辑；提示词文件追加和复制行仍保持原有顺序语义。
- 工作流 JSON 导入修复：修复未指定生成类型时自动解析接口因 Python 局部导入作用域冲突返回 500 的问题，并增加自动检测分支回归测试。
- 图片遮罩编辑器：在图片输入参数上绘制遮罩，支持画笔/橡皮擦/油漆桶、笔刷大小/不透明度/硬度、Shift+点击画直线、撤销重做、滚轮缩放、空格+拖拽平移、双指触摸缩放平移，遮罩保存后下次打开可继续编辑。
- 遮罩与 ComfyUI 集成：遮罩导出为纯黑白 PNG（白色=遮罩区域），后端自动插入 LoadImageMask 节点从 red 通道提取遮罩，支持 DrawMaskOnImage 等需要独立 mask 输入的工作流节点，同时将 LoadImage 的 MASK 输出连接重定向到 LoadImageMask。
- 图片预览全屏模式：MediaViewer 改为全屏遮罩模式，支持鼠标滚轮缩放（以鼠标位置为中心）、单指/双指拖拽平移、双击切换缩放、双指 pinch-to-zoom（移动端）、ESC 关闭。
- 图片预览快速操作：在预览图片时可直接选择”图片操作”（排除文生图）或”生成视频”（排除文生视频），选择后跳转到对应生成页面并自动填入该图片作为第一个图片参数的输入。
- 图片基础编辑器：旋转（90°递增）、水平/垂直翻转、裁剪（8 个拖拽手柄 + 常用比例快捷按钮 1:1/4:3/16:9/9:16 等）、视图缩放平移，编辑后另存为新素材不修改原图。
- 视频帧控制：视频预览中可拖动进度条定位、截取首帧/尾帧/当前帧并保存到素材库。
- 视频剪辑与合并：在视频预览中设置开始/结束时间进行剪辑，或在素材库选中多个视频进行合并，结果保存为新视频素材。
- 素材库批量操作：选中素材后底部悬浮操作栏显示移动、图片操作、生成视频、合并视频、移入回收站按钮，操作后自动刷新。
- 素材库软删除与回收站：批量删除改为软删除（移入回收站），回收站页面显示缩略图、支持点击预览、单个恢复/永久删除、一键清空回收站。
- 提示词库快速保存：在生成页面、任务列表、任务详情中的提示词旁提供”存入提示词库”按钮，自动按媒体类型（图片/视频）创建或匹配分类并保存。
- 提示词复制按钮：所有只读显示提示词的位置（任务列表、批次详情、系统概览、提示词库、素材详情）均提供一键复制按钮。
- 任务列表显示工作流名称：后端批量查询 WorkflowVersion→Workflow 的 name 并附加到 TaskOut。
- 任务再检查功能：对”ComfyUI 已丢失该任务记录”的失败任务提供”再检查”按钮，先重新获取 ComfyUI history，若仍丢失则按文件名规律搜索输出文件。
- 切换工作流保留素材：生成页面切换工作流时，图片/视频/音频参数按类型匹配迁移到新工作流（即使 key 不同），同时迁移遮罩关联字段。
- 选项来源自动填默认值：在工作流参数配置中选择选项来源后自动填入系统维护项的默认值；选择工作节点和参数路径后自动推断参数名称、标识和类型。
- 素材预览按钮：生成页面的图片参数旁提供”预览”按钮，点击打开全屏 MediaViewer 查看已选素材。
- 自定义日历组件：任务管理日期选择从原生 date input 改为自定义日历弹窗，支持月份切换、快捷日期按钮，移动端友好。
- 移动端遮罩编辑器优化：底部浮动工具栏（画笔/橡皮/填充/移动 + 笔刷滑块 + 操作按钮），单指绘制、双指缩放平移、双击重置视图。
- 移动端素材库目录树优化：目录面板默认折叠，点击展开到 50vh 可滚动，选择目录后自动折叠。
- 移动端素材库悬浮操作栏位置调整：避免与底部主菜单重叠。
- 缩略图与存储路径修复：存储路径从 SHA256 前 8 位改为前 16 位避免碰撞导致缩略图与实际图片不对应；素材库加载加版本计数器防止竞态导致重复显示。

## 技术栈

| 层级 | 技术 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Pinia、Naive UI、Tailwind CSS |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy 2、Pydantic、HTTPX、WebSocket |
| 数据库 | SQLite（默认），可扩展 PostgreSQL |
| 文件存储 | 本地文件系统 `backend/data/resources` |
| 媒体处理 | Pillow、FFmpeg/FFprobe |
| 部署 | Docker、Docker Compose、Nginx |

## 项目结构

```text
comfyui-console/
├─ backend/
│  ├─ app/                 # FastAPI 应用、调度器、ComfyUI 客户端
│  ├─ alembic/             # 数据库迁移
│  ├─ tests/               # 后端测试
│  ├─ data/                # SQLite 数据库和素材文件（运行后生成）
│  ├─ .env.example         # 环境变量示例
│  ├─ Dockerfile
│  └─ pyproject.toml
├─ frontend/
│  ├─ src/                 # Vue 页面、路由、API、V1 页面与 V2 独立模块
│  ├─ nginx.conf           # 生产反向代理配置
│  ├─ Dockerfile
│  └─ package.json
├─ docs/                   # 架构、部署、V1 基线、V2 计划与迭代验收记录
├─ docker-compose.yml
└─ README.md
```

## 快速部署：Docker Compose

### 1. 前置条件

- Docker 20.10+。
- Docker Compose v2（使用 `docker compose` 命令）。
- 至少一个可访问的 ComfyUI 实例。
- 建议预留足够磁盘空间保存生成结果。

ComfyUI 与本项目可以部署在同一台机器或不同机器。ComfyUI 必须允许平台访问其 HTTP API。

### 2. 获取项目

```bash
git clone https://github.com/lifeye-sh/comfyui-console.git
cd comfyui-console
```

### 3. 创建后端配置

Linux/macOS：

```bash
cp backend/.env.example backend/.env
```

Windows PowerShell：

```powershell
Copy-Item backend/.env.example backend/.env
```

编辑 `backend/.env`：

```dotenv
COMFY_CONSOLE_DEBUG=false
COMFY_CONSOLE_SHORT_DRAMA_ENABLED=true
COMFY_CONSOLE_DATABASE_URL=sqlite:///./data/app.db
COMFY_CONSOLE_STORAGE_PATH=./data/resources
COMFY_CONSOLE_SECRET_KEY=请替换为足够长的随机密钥
COMFY_CONSOLE_ADMIN_USERNAME=admin
COMFY_CONSOLE_ADMIN_PASSWORD=请替换为强密码
```

V2 是前端构建时功能，需在 `frontend/.env.local` 中启用。可以从示例文件复制：

Linux/macOS：

```bash
cp frontend/.env.example frontend/.env.local
```

Windows PowerShell：

```powershell
Copy-Item frontend/.env.example frontend/.env.local
```

编辑为：

```dotenv
VITE_UI_V2_ENABLED=true
VITE_UI_V2_ROLLOUT_PERCENT=100
VITE_UI_V2_DEFAULT=true
VITE_UI_V2_1_SHORT_DRAMA_ENABLED=true
```

修改 V2 开关后必须重新构建前端镜像。V2 是默认界面；紧急回滚时可设置 `VITE_UI_V2_ENABLED=false`。

可以使用下面的命令生成随机密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

注意：`docker-compose.yml` 会只读挂载 `backend/.env`，因此该文件必须存在。

### 4. 构建并启动

在项目根目录执行：

```bash
docker compose up -d --build
```

启动后访问：

- Web 管理界面：`http://服务器IP/`
- V2 界面：启用 V2 后通过 V1 的“进入新版”入口访问，或登录后打开 `http://服务器IP/v2`
- 后端健康检查：`http://服务器IP:8000/health`
- API 文档：`http://服务器IP:8000/docs`

本机部署时可访问 `http://127.0.0.1/`。

### 5. 查看运行状态

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
```

健康检查预期返回：

```json
{"status":"ok","app":"comfyui-console","version":"0.1.0"}
```

### 6. 停止或重启

```bash
docker compose stop
docker compose start
```

停止并移除容器（不会删除绑定目录中的数据）：

```bash
docker compose down
```

不要在未备份的情况下删除 `backend/data`，该目录包含数据库和素材文件。

## 首次登录和初始化

后端第一次启动时会自动创建管理员、内置生成类型、尺寸选项、提示词分类和素材系统目录。

管理员账号由以下环境变量决定：

```dotenv
COMFY_CONSOLE_ADMIN_USERNAME=admin
COMFY_CONSOLE_ADMIN_PASSWORD=你的强密码
```

如果没有配置，程序默认使用 `admin / admin123`。默认密码只适合本地测试，生产环境必须在首次启动前通过 `.env` 修改。

管理员种子仅在账号不存在时创建；已有管理员不会因修改 `.env` 自动更换密码。

## 配置小说转剧本 AI

管理员登录 V2 后，进入“系统配置 → AI 模型配置”，添加一个 OpenAI 兼容服务，填写名称、API Base URL、模型名称和 API Key，并设为默认配置。保存后可先执行连接测试。

项目使用流程：

1. 在“短剧项目”中新建项目并导入小说。
2. 进入“剧本改编”，选择模型并启动 AI 分析；长文本会按章节和段落分块处理。
3. 检查并确认故事档案，再生成 AI 改编方案。
4. 确认候选方案后，继续维护世界设定、分镜和镜头生产。

API Key 只以加密形式保存，列表接口仅返回掩码。加密密钥来自 `COMFY_CONSOLE_SECRET_KEY`，生产部署后必须保持该值稳定，否则历史 API Key 将无法解密。未配置模型时仍可使用页面中明确标注的“本地规则”作为降级方案。

## 连接 ComfyUI 节点

登录后进入 V1“节点管理”或 V2“系统配置 → 运行监控”，添加和检查 ComfyUI 节点：

| 配置项 | 示例 |
| --- | --- |
| 名称 | 本地 ComfyUI |
| HTTP 地址 | `http://192.168.3.51:8188` |
| WebSocket 地址 | 通常由 HTTP 地址和 ComfyUI `/ws` 自动使用 |
| 最大并发 | 建议从 `1` 开始，根据显存调整 |

保存后执行连接测试，再启用节点。

任务提交后先进入平台数据库队列，再由后端独立调度线程派发到可用节点。请不要绕过平台直接修改同一任务的 ComfyUI 队列；当调度异常时，管理员可在“运行监控”查看调度器心跳、节点探测错误和占用执行槽的任务。

### Docker 网络注意事项

如果 ComfyUI 运行在 Docker 宿主机上，后端容器中的 `127.0.0.1` 指向后端容器本身，而不是宿主机。因此不要配置：

```text
http://127.0.0.1:8188
```

应使用以下地址之一：

- Windows/macOS Docker Desktop：`http://host.docker.internal:8188`
- 局域网地址：`http://192.168.x.x:8188`
- 同一个 Compose 网络中的服务名：`http://comfyui:8188`

如果使用局域网地址，请确认 ComfyUI 监听 `0.0.0.0`，防火墙允许 8188 端口，并且后端服务器能够访问该地址。

可从宿主机先测试：

```bash
curl http://192.168.3.51:8188/system_stats
```

也可以从后端容器测试：

```bash
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:8188/system_stats').status)"
```

## 本地开发安装

### 1. 环境要求

- Python 3.11 或更高版本。
- Node.js 20 或更高版本。
- npm 10+。
- FFmpeg（视频首帧、抽帧和元数据处理需要）。
- 可访问的 ComfyUI 实例。

确认版本：

```bash
python --version
node --version
npm --version
ffmpeg -version
```

### 2. 启动后端

Linux/macOS：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Windows PowerShell：

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

后端地址：

- API：`http://127.0.0.1:8000/api/v1`
- Swagger：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

### 3. 启动前端

打开另一个终端：

```bash
cd frontend
npm install
npm run dev
```

访问 `http://127.0.0.1:5173/`。Vite 会将 `/api`、`/ws` 和 `/s` 代理到 `http://127.0.0.1:8000`。

### 4. 运行检查

后端测试：

```bash
cd backend
pytest -q
```

前端类型检查和生产构建：

```bash
cd frontend
npm run typecheck
npm run build
```

### 5. V1/V2 切换

V2 由以下前端构建变量控制：

| 变量 | 说明 |
| --- | --- |
| `VITE_UI_V2_ENABLED` | V2 总开关；默认启用，显式设为 `false` 时访问 `/v2` 会返回 V1 |
| `VITE_UI_V2_ROLLOUT_PERCENT` | 0–100 的浏览器稳定哈希灰度比例 |
| `VITE_UI_V2_DEFAULT` | 未保存个人偏好时的默认入口；默认 `true`，即进入 V2 |
| `VITE_UI_V2_1_SHORT_DRAMA_ENABLED` | V2.1 短剧项目菜单和路由开关，默认启用 |

开发环境启用方式：

```bash
cd frontend
cp .env.example .env.local
# 默认已启用；如从旧配置升级，将 VITE_UI_V2_ENABLED 和 VITE_UI_V2_DEFAULT 改为 true
npm run dev
```

访问根路径 `/` 或登录成功后默认进入 `/v2`。用户仍可通过 V2 顶部的“切换旧版”进入 `/v1`，并保留个人选择。

Windows PowerShell 使用 `Copy-Item .env.example .env.local`。生产回退时将总开关设为 `false` 并重新构建前端，后端数据和任务无需回滚。

## 环境变量

所有后端环境变量以 `COMFY_CONSOLE_` 开头。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `COMFY_CONSOLE_APP_NAME` | `comfyui-console` | 应用名称 |
| `COMFY_CONSOLE_VERSION` | `0.1.0` | API 显示版本 |
| `COMFY_CONSOLE_DEBUG` | `true` | 调试模式，生产应设为 `false` |
| `COMFY_CONSOLE_SHORT_DRAMA_ENABLED` | `true` | V2.1 短剧模块运行开关；关闭后状态接口会通知前端回退 |
| `COMFY_CONSOLE_STORY_WORKER_POLL_SECONDS` | `1` | 独立 Story Worker 的队列轮询间隔（秒） |
| `COMFY_CONSOLE_STORY_WORKER_TIMEOUT_SECONDS` | `300` | 创作任务心跳超时回收阈值（秒） |
| `COMFY_CONSOLE_STORY_WORKER_MAX_RETRIES` | `2` | Worker 中断后的自动恢复次数上限 |
| `COMFY_CONSOLE_DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy 数据库地址 |
| `COMFY_CONSOLE_STORAGE_PATH` | `./data/resources` | 素材存储目录 |
| `COMFY_CONSOLE_SECRET_KEY` | 开发默认值 | JWT 签名密钥，生产必须修改 |
| `COMFY_CONSOLE_ALGORITHM` | `HS256` | JWT 算法 |
| `COMFY_CONSOLE_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access Token 有效期 |
| `COMFY_CONSOLE_REFRESH_TOKEN_EXPIRE_MINUTES` | `10080` | Refresh Token 有效期，默认 7 天 |
| `COMFY_CONSOLE_ADMIN_USERNAME` | `admin` | 首次启动管理员用户名 |
| `COMFY_CONSOLE_ADMIN_PASSWORD` | `admin123` | 首次启动管理员密码 |

`COMFY_CONSOLE_CORS_ORIGINS` 是列表类型。生产环境通常由同域 Nginx 代理，无需浏览器跨域；如果前后端分开部署，需要按 Pydantic Settings 支持的 JSON 列表格式配置允许来源。

## 数据和备份

Docker 默认持久化位置：

```text
backend/data/app.db             SQLite 数据库
backend/data/resources/         上传素材和生成结果
```

### 备份

建议先短暂停止后端，保证 SQLite 备份一致：

```bash
docker compose stop backend
```

然后复制整个 `backend/data` 目录到备份位置，完成后恢复：

```bash
docker compose start backend
```

生产环境建议定期执行自动备份，并同时备份数据库和素材目录，二者必须保持对应关系。

任务输出默认归档到用户素材库的：

```text
任务结果 / YYYY-MM / YYYY-MM-DD
```

同一天的任务结果直接存放在日期目录，任务归属通过素材详情中的生成参数以及任务资源关联查询，不再额外创建任务编号目录。

### 升级

1. 备份 `backend/data` 和 `backend/.env`。
2. 获取新版本代码。
3. 重新构建并启动：

```bash
docker compose up -d --build
```

4. 检查健康状态和日志：

```bash
docker compose ps
docker compose logs --tail=200 backend
```

当前应用启动时会创建缺失的表，并对部分 SQLite 字段执行兼容升级。生产环境引入 PostgreSQL 或执行跨版本升级时，应优先按 Alembic 迁移说明操作并先在备份环境验证。

当前版本新增了生成类型配置版本和运行监控相关迁移。升级前建议执行：

```bash
cd backend
alembic upgrade head
```

Docker 部署可使用：

```bash
docker compose exec backend alembic upgrade head
```

应用启动仍包含 SQLite 开发态兼容升级，但正式部署应以 Alembic 为准。

## 生产部署建议

- 将 `COMFY_CONSOLE_DEBUG` 设置为 `false`。
- 修改 JWT 密钥和默认管理员密码。
- 在前端 Nginx 之前配置 HTTPS（Nginx、Caddy 或 Traefik 均可）。
- 仅向可信网络开放后端 8000 端口；公网只开放 80/443 更安全。
- 使用防火墙限制 ComfyUI 8188 端口的访问来源。
- 定期备份数据库和素材文件。
- 大规模并发时评估 PostgreSQL、对象存储及独立队列。
- 根据 GPU 显存为每个节点设置合理的最大并发，初始建议为 1。

如果不希望后端 8000 端口直接暴露，可从 `docker-compose.yml` 删除后端 `ports`，只通过前端 Nginx 的 `/api` 和 `/ws` 访问后端。

## 常见问题

### 节点测试失败或任务一直等待

1. 从后端运行环境访问 `/system_stats`，确认网络连通。
2. Docker 部署不要使用宿主机的 `127.0.0.1:8188`。
3. 确认节点已启用、并发数大于 0。
4. 检查 ComfyUI 是否监听外部地址及防火墙规则。
5. 查看后端日志：`docker compose logs -f backend`。

### ComfyUI 执行成功，但平台任务失败

通常发生在输出回收阶段。检查：

- ComfyUI `/history/{prompt_id}` 是否可访问。
- 输出节点是否在工作流输出映射中。
- `/view` 返回的文件是否可下载。
- 后端是否有写入 `backend/data/resources` 的权限。
- 磁盘空间是否充足。

### 视频没有首帧或不能播放

- 确认后端环境安装了 FFmpeg 和 FFprobe。
- 检查视频编码是否被浏览器支持。
- 查看资源接口是否成功返回文件和缩略图。
- Docker 镜像已经安装 FFmpeg，修改镜像后需重新构建。

### 修改 `.env` 后没有生效

重建或重启后端容器：

```bash
docker compose up -d --force-recreate backend
```

管理员账号已经存在时，修改种子密码不会覆盖数据库中的现有密码。

### V2 菜单没有显示或访问 `/v2` 返回 V1

V2 是前端构建时开关，修改 `frontend/.env.local` 后必须重新构建前端：

```bash
docker compose up -d --build frontend
```

确认 `VITE_UI_V2_ENABLED=true`，并检查 `VITE_UI_V2_ROLLOUT_PERCENT` 没有设置为 `0`。

### 有排队任务时登录缓慢或任务停止执行

当前版本已将 Dispatcher 放到独立线程。管理员进入 V2“系统配置 → 运行监控”检查：

- 调度器是否显示“运行中”并持续更新心跳。
- ComfyUI 节点是否在线，最近探测错误是什么。
- 是否存在长期停留在 `DISPATCHING`、`QUEUED` 或 `RUNNING` 的任务。
- 必要时对异常任务执行“释放执行槽”或“重新提交”。

如果整个调度器未运行，检查后端启动日志中的 `Dispatcher started`，并重启后端服务。

### 端口冲突

修改 `docker-compose.yml` 左侧宿主机端口。例如：

```yaml
ports:
  - "6799:80"
```

此时 Web 访问地址变为 `http://服务器IP:6799/`。

## API 与文档

- 在线 API 文档：后端启动后访问 `/docs`。
- [系统架构](docs/architecture.md)
- [功能清单](docs/feature-list.md)
- [功能详细规格](docs/feature-specification.md)
- [开发计划](docs/development-plan.md)
- [部署说明](docs/deployment.md)
- [V2 产品、界面详细设计与开发计划](docs/v2-product-ui-development-plan.md)
- [V2 开发执行计划](docs/v2-development-execution-plan.md)
- [V2 Iteration 1 验收记录](docs/v2-iteration-1-acceptance-2026-08-13.md)
- [V2 Iteration 2 验收记录](docs/v2-iteration-2-acceptance-2026-08-13.md)
- [V2 Iteration 3 验收记录](docs/v2-iteration-3-acceptance-2026-08-13.md)
- [V2 Iteration 5 验收记录](docs/v2-iteration-5-acceptance-2026-08-13.md)
- [V2 Iteration 6 验收记录](docs/v2-iteration-6-acceptance-2026-08-13.md)
- [V2 Iteration 7 验收记录](docs/v2-iteration-7-acceptance-2026-08-13.md)
- [V2 Iteration 8 验收记录](docs/v2-iteration-8-acceptance-2026-08-13.md)

## 安全说明

本项目能够连接 ComfyUI、上传文件并执行工作流。请只配置可信的 ComfyUI 节点和工作流，不要将默认密码、JWT 密钥或未受保护的 ComfyUI API 暴露到公网。

## License

仓库当前未提供独立许可证文件。正式分发或开源前，请补充明确的 License。

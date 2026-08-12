# ComfyUI Console

ComfyUI Console 是一个面向本地或远程 ComfyUI 节点的统一生成管理平台，提供工作流管理、参数映射、批量任务、任务调度、图片/视频/音频素材管理和移动端访问能力。

项目地址：[https://github.com/lifeye-sh/comfyui-console](https://github.com/lifeye-sh/comfyui-console)

当前 V1 为稳定运行版本。新版菜单与 Glassmorphism 界面作为 V2 独立规划，不会替换或破坏 V1；详细方案参见 [V2 产品、界面详细设计与开发计划](docs/v2-product-ui-development-plan.md)。

## 主要功能

- 图片、视频和音频生成类型动态菜单。
- 文生图、图生图、文生视频、图生视频、动作迁移等生成页面。
- ComfyUI API JSON 工作流导入、版本管理、参数自动匹配和手工映射。
- 每种生成类型只显示和管理本类型工作流。
- 批量任务行、逐行生成、批量生成、复制和提示词文件导入。
- 图片、视频和音频输入支持上传或从素材库选择，并提供预览。
- 任务管理、状态过滤、任务详情、执行事件、结果预览和重新生成。
- 在任务详情修改参数，并创建一条新任务执行，不改变原任务。
- 素材库无限级目录、任务结果自动归档、多媒体预览和生成参数查看。
- ComfyUI 多节点管理、并发调度、失败重试和结果自动回收。
- 提示词库、参数方案、尺寸选项、审计日志、分享和回收站。
- 响应式 Web 页面，支持桌面浏览器和移动端访问。

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
│  ├─ src/                 # Vue 页面、路由、API 和组件
│  ├─ nginx.conf           # 生产反向代理配置
│  ├─ Dockerfile
│  └─ package.json
├─ docs/                   # 架构、功能、部署和 V2 规划文档
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
COMFY_CONSOLE_DATABASE_URL=sqlite:///./data/app.db
COMFY_CONSOLE_STORAGE_PATH=./data/resources
COMFY_CONSOLE_SECRET_KEY=请替换为足够长的随机密钥
COMFY_CONSOLE_ADMIN_USERNAME=admin
COMFY_CONSOLE_ADMIN_PASSWORD=请替换为强密码
```

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

## 连接 ComfyUI 节点

登录后进入“节点管理”，添加 ComfyUI 节点：

| 配置项 | 示例 |
| --- | --- |
| 名称 | 本地 ComfyUI |
| HTTP 地址 | `http://192.168.3.51:8188` |
| WebSocket 地址 | 通常由 HTTP 地址和 ComfyUI `/ws` 自动使用 |
| 最大并发 | 建议从 `1` 开始，根据显存调整 |

保存后执行连接测试，再启用节点。

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

## 环境变量

所有后端环境变量以 `COMFY_CONSOLE_` 开头。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `COMFY_CONSOLE_APP_NAME` | `comfyui-console` | 应用名称 |
| `COMFY_CONSOLE_VERSION` | `0.1.0` | API 显示版本 |
| `COMFY_CONSOLE_DEBUG` | `true` | 调试模式，生产应设为 `false` |
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

## 安全说明

本项目能够连接 ComfyUI、上传文件并执行工作流。请只配置可信的 ComfyUI 节点和工作流，不要将默认密码、JWT 密钥或未受保护的 ComfyUI API 暴露到公网。

## License

仓库当前未提供独立许可证文件。正式分发或开源前，请补充明确的 License。

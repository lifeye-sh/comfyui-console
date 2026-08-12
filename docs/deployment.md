# comfyui-console 部署指南

## 开发模式

### 后端
```bash
cd backend
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### 前端
```bash
cd frontend
npm install
npm run dev                   # http://127.0.0.1:5173
```

### 测试
```bash
cd backend && pytest
```

## Docker Compose 部署

### 前置条件
- Docker 20+ 与 Docker Compose v2+
- 本机或远程 ComfyUI 实例运行正常（默认 `http://127.0.0.1:8188`）

### 步骤

1. 配置后端环境变量：
   ```bash
   cp backend/.env.example backend/.env
   # 编辑 .env，至少修改 COMFY_CONSOLE_SECRET_KEY
   ```

2. 一键启动：
   ```bash
   docker compose up -d --build
   ```

3. 访问 `http://<服务器IP>` 即可使用。

4. 查看日志：
   ```bash
   docker compose logs -f backend
   docker compose logs -f frontend
   ```

5. 停止：
   ```bash
   docker compose down
   ```

### 数据持久化
- SQLite 数据库：`backend/data/app.db`（挂载卷）
- 资源文件：`backend/data/resources/`（挂载卷）
- 如需 PostgreSQL，修改 `.env` 中 `COMFY_CONSOLE_DATABASE_URL` 并在 compose 中添加 db 服务

### ComfyUI 节点配置
启动后在「节点管理」页面添加 ComfyUI 节点：
- 名称：本地节点
- HTTP 地址：`http://127.0.0.1:8188`（或远程地址）
- WebSocket 地址：`ws://127.0.0.1:8188/ws`
- 并发数：1（视显存而定）

### 默认管理员
首次启动自动创建：`admin / admin123`，请在生产环境中及时修改密码。

## 生产环境注意事项

1. **修改密钥**：`COMFY_CONSOLE_SECRET_KEY` 必须改为随机值
2. **修改管理员密码**：登录后在用户管理中修改
3. **HTTPS**：在 nginx 前面加 TLS 终端（Caddy / Traefik / nginx + certbot）
4. **PostgreSQL**：高并发场景建议切换到 PostgreSQL
5. **Redis**：队列性能瓶颈时切换 `QueueProvider` 为 Redis Streams
6. **MinIO/S3**：资源量大时切换 `StorageProvider` 为 S3 兼容存储
7. **ffmpeg**：视频抽帧功能需要后端环境安装 ffmpeg（Docker 镜像基于 python:3.11-slim，需在 Dockerfile 中添加 `apt-get install ffmpeg`）
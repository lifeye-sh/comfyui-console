# CLAUDE.md — comfyui-console 项目上下文（给 Claude Code）

## 项目简介

comfyui-console 是面向本地或远程 ComfyUI 实例的统一管理平台：工作流管理、批量任务排队调度、输入输出资源统一管理与同步共享、移动端 H5。详见 `docs/architecture.md`。

## 文档地图（实现前必读对应章节）

- `docs/architecture.md` v0.2 — 系统架构、领域模型、数据模型、API 概览
- `docs/feature-list.md` v0.2 — 功能清单与菜单结构
- `docs/feature-specification.md` v0.3 — 功能详细规格（页面/字段/校验/验收）
- `docs/development-plan.md` v1.0 — 任务卡 CC-00 ~ CC-36

## 技术栈

- 后端：Python 3.11+ / FastAPI / SQLAlchemy 2.x / Alembic / httpx / websockets
- 前端：Vue 3 + Vite + TypeScript + Pinia + Vue Router + Naive UI + Tailwind CSS

## 目录结构

```
comfyui-console/
├── docs/                 # 设计文档（本文件指向的章节）
├── backend/              # FastAPI 后端
│   ├── app/              # main / config / api / ws / core / models / schemas / services / comfy / queue / storage
│   ├── alembic/          # 迁移
│   ├── tests/
│   └── pyproject.toml
└── frontend/             # Vue3 SPA
    └── src/              # api / ws / stores / views / components / router / styles
```

## 常用命令

```bash
# 后端
cd backend && uvicorn app.main:app --reload --port 8000
cd backend && pytest
cd backend && alembic upgrade head

# 前端
cd frontend && npm run dev
cd frontend && npm run build
cd frontend && npm run typecheck
```

## 编码规范

- Python：类型注解必填；异步优先（async def）；服务层注入依赖；不裸用 `print`，用 `logging`。
- 前端：Composition API + `<script setup lang="ts">`；状态走 Pinia；不使用 localStorage 存敏感信息。
- 提交：约定式 `feat(scope): CC-XX 描述` / `docs: 描述`；一卡一提交。

## 当前阶段

- 已完成：Phase 0（CC-00）、Phase 1（CC-01~11）、Phase 2（CC-13~21）、Phase 3（CC-23~29）、Phase 4（CC-31~36：移动端压缩/通知/设置页/Docker Compose/测试/部署文档）
- 全部 37 张任务卡（CC-00 ~ CC-36）代码已写完，待运行时验收
- 部署文档：`docs/deployment.md`
- 任务看板：见 `docs/development-plan.md` §11

## 禁忌

- 不修改 docs 文件的版本号与编号语义（架构/功能清单/规格/计划）。
- 不绕过任务卡的验收命令；验收未通过不进入下一卡。
- 不在生成页硬编码生成类型；生成页必须配置驱动（架构 §5.2）。
- 不直接打到 ComfyUI 节点的原生队列；任务先入平台队列再调度（架构 §1.1）。

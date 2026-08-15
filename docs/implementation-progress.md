# Autonomous SWE Agent 实现进度文档

> 本文档记录项目当前实现进度，随开发持续更新。
>
> 关联文档：[产品设计](./autonomous-swe-agent.md) · [实现路线对比](./implementation-routes.md) · [简历项目实现指南](./resume-project-guide.md)

## 1. 项目概述

Autonomous SWE Agent 是一个面向软件工程任务的自主 AI Agent 平台。用户输入自然语言开发任务，Agent 自动完成代码分析、定位问题、修改代码、执行测试并创建 PR。

**技术选型（已确认）：**

| 层 | 技术 |
| --- | --- |
| 仓库结构 | Monorepo（backend + frontend 同仓） |
| 后端 | FastAPI + LangGraph + Celery |
| 依赖管理 | uv（Python 3.12） |
| 数据库 | PostgreSQL（pgvector） |
| 缓存/队列 | Redis |
| 前端 | Next.js 14 + TypeScript + TailwindCSS |
| 沙箱 | E2B（预留 Docker 切换） |
| LLM | OpenAI / Claude 多模型路由 |

---

## 2. 总体进度

当前处于 **「项目骨架初始化」阶段**，核心目标已完成：目录结构、基础配置文件、可运行的最小后端入口与前端页面均已就位。

| 阶段 | 状态 |
| --- | --- |
| 项目骨架初始化 | ✅ 已完成 |
| 基础设施编排（Docker） | ✅ 已完成（配置文件） |
| 单 Agent 闭环（改文件 → 跑测试） | ⏳ 未开始 |
| 工具系统（Git/File/Terminal） | ⏳ 未开始 |
| 多 Agent 编排 | ⏳ 未开始 |
| RAG 代码检索 | ⏳ 未开始 |
| 评测体系 | ⏳ 未开始 |
| 前端完整页面 | ⏳ 未开始 |

---

## 3. 已完成模块详情

### 3.1 根级配置

| 文件 | 说明 | 状态 |
| --- | --- | --- |
| `docker-compose.yml` | 编排 PostgreSQL(pgvector/pgvector:pg16) + Redis(redis:7-alpine)，含健康检查与数据卷 | ✅ |
| `.gitignore` | 忽略 Python/Node/Env/IDE 等产物 | ✅ |

### 3.2 后端（backend/）

| 文件/目录 | 说明 | 状态 |
| --- | --- | --- |
| `pyproject.toml` | uv 依赖声明：fastapi、uvicorn、langgraph、langchain-openai/anthropic、celery、redis、sqlalchemy、psycopg、pgvector、httpx；dev 组含 pytest、ruff | ✅ |
| `.python-version` | 锁定 Python 3.12 | ✅ |
| `.env.example` | 环境变量模板（数据库、Redis、LLM、沙箱配置） | ✅ |
| `app/main.py` | FastAPI 入口，`create_app()` 工厂函数，注册 health + tasks 路由 | ✅ |
| `app/core/config.py` | `Settings` 配置类（pydantic-settings），`get_settings()` 带 lru_cache | ✅ |
| `app/api/routes/health.py` | `GET /health` 健康检查接口 | ✅ |
| `app/api/routes/tasks.py` | `GET/POST /api/v1/tasks` 占位接口 | ✅ |
| `app/worker/celery_app.py` | Celery 实例，broker/backend 指向 Redis，时区 Asia/Shanghai | ✅ |
| `app/agents/` | 多 Agent 编排目录（空占位） | ⏳ |
| `app/tools/` | 工具系统目录（空占位） | ⏳ |
| `app/rag/` | 代码检索目录（空占位） | ⏳ |
| `app/sandbox/` | 沙箱执行目录（空占位） | ⏳ |
| `app/db/` | 数据库连接/向量存储目录（空占位） | ⏳ |
| `app/models/` | ORM 模型目录（空占位） | ⏳ |
| `tests/` | 测试目录（空占位） | ⏳ |

### 3.3 前端（frontend/）

| 文件/目录 | 说明 | 状态 |
| --- | --- | --- |
| `package.json` | Next.js 14.2.5 + React 18 + TailwindCSS 3.4 依赖与脚本 | ✅ |
| `tsconfig.json` | Next.js 标准 TS 配置，`@/*` 路径别名指向 `src/*` | ✅ |
| `next.config.mjs` | Next 配置（reactStrictMode） | ✅ |
| `tailwind.config.ts` | Tailwind 内容扫描 `src/**/*` | ✅ |
| `postcss.config.mjs` | tailwindcss + autoprefixer | ✅ |
| `.env.example` | 后端 API 地址模板 | ✅ |
| `src/app/layout.tsx` | 根布局，标题「Autonomous SWE Agent」 | ✅ |
| `src/app/page.tsx` | 首页占位（标题 + 副标题） | ✅ |
| `src/app/globals.css` | Tailwind 三件套导入 | ✅ |

---

## 4. 待实现模块（按优先级）

### 优先级 1：单 Agent 闭环

让一个 Coding Agent 具备「改文件 → 跑测试」的最小能力，是后续多 Agent 的基础。

- `app/tools/`：工具协议（base）与 Git/File/Terminal 实现
- `app/sandbox/`：E2B 沙箱接入
- `app/agents/`：单个 ReAct Coding Agent

### 优先级 2：编排与状态

- 多 Agent 编排（Planner → Coding → Testing → Review）
- 显式状态机 + 失败重试 + 人工审批
- 任务持久化（PostgreSQL）

### 优先级 3：检索与评测

- `app/rag/`：tree-sitter 分块 + 混合检索 + 重排序
- `app/db/`：SQLAlchemy + pgvector 接入
- 评测集与解决率指标

### 优先级 4：前端完整化

- Dashboard / Agent Chat / Task Timeline 页面
- 流式响应 + Diff View

---

## 5. 当前可运行能力

后端最小入口已就绪，可运行以下验证：

```powershell
# 起基础设施
docker compose up -d

# 后端
cd backend
uv sync
uv run uvicorn app.main:app --reload
# 访问 http://localhost:8000/health 返回 {"status":"ok"}
# 访问 http://localhost:8000/api/v1/tasks 返回 []

# 前端
cd frontend
npm install
npm run dev
# 访问 http://localhost:3000 显示占位首页
```

---

## 6. 下一步计划

1. 实现工具系统（Git/File/Terminal）与沙箱接入
2. 落地单 Agent 闭环，跑通「改文件 → 跑测试」
3. 引入状态机与多 Agent 编排
4. 建立评测集与量化指标

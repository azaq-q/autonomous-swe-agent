# Autonomous SWE Agent 实现进度文档

> 本文档记录项目当前实现进度，随开发持续更新。
>
> 关联文档：[产品设计](./autonomous-swe-agent.md) · [实现路线对比](./implementation-routes.md) · [简历项目实现指南](./resume-project-guide.md) · [本地环境安装与运行步骤](./local-setup.md)

## 1. 项目概述

Autonomous SWE Agent 是一个面向软件工程任务的自主 AI Agent 平台。用户输入自然语言开发任务，Agent 自动完成代码分析、定位问题、修改代码、执行测试并创建 PR。

**技术选型（已确认）：**

| 层 | 技术 |
| --- | --- |
| 仓库结构 | Monorepo（backend + frontend 同仓） |
| 后端 | FastAPI + LangGraph + Celery |
| 依赖管理 | uv（Python 3.12） |
| 数据库 | 默认 SQLite（无 Docker 可跑）；生产 PostgreSQL（pgvector） |
| 缓存/队列 | Redis |
| 前端 | Next.js 14 + TypeScript + TailwindCSS |
| 沙箱 | 本地 subprocess / Docker / E2B（可切换） |
| LLM | OpenAI 兼容（含 DeepSeek）/ Claude 多模型路由 |

---

## 2. 总体进度

核心闭环（P1-P5）已全部实现，各阶段均通过单元测试并提交 git。项目已端到端跑通：SQLite 自动建表 + 本地沙箱 + 任务后台执行 + 前端轮询。

| 阶段 | 状态 | 提交 |
| --- | --- | --- |
| 项目骨架初始化 | ✅ 完成 | `df8dc06` |
| P1 单 Agent 闭环 | ✅ 完成 | `5eef38a` |
| P2 编排与状态 | ✅ 完成 | `8bd905f` |
| P3 检索与评测 | ✅ 完成 | `9a7b101` |
| P4 前端完整化 | ✅ 完成 | `006c3fb` |
| P5 任务持久化与异步执行 | ✅ 完成 | `bdcfcc7` |
| P6 多沙箱与多模型接入 | ✅ 完成 | `42c5b59` |

单元测试：**26 passed**（后端）。

---

## 3. 已完成模块详情

### 3.1 基础设施

| 文件 | 说明 |
| --- | --- |
| `docker-compose.yml` | PostgreSQL(pgvector/pgvector:pg16) + Redis(redis:7-alpine) |
| `.gitignore` | Python / Node / Env / IDE 忽略规则 |

### 3.2 后端核心（backend/app/）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 配置 | `core/config.py` | pydantic-settings 配置（数据库/Redis/LLM/沙箱/workdir） |
| LLM | `core/llm.py` | 多模型工厂（OpenAI 兼容含 DeepSeek / Anthropic） |
| 应用入口 | `main.py` | FastAPI 工厂，注册路由 + CORS + 启动建表（init_db） |
| 任务 API | `api/routes/tasks.py` | 任务创建/列表/查询（数据库持久化 + 后台执行） |
| 任务执行器 | `services/executor.py` | 后台执行任务：无 LLM key 走 mock，有则走编排 |
| 健康检查 | `api/routes/health.py` | `GET /health` |

### 3.3 沙箱与工具（P1 / P6）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 沙箱抽象 | `sandbox/base.py` | `CommandResult` + `Sandbox` 协议 |
| 本地沙箱 | `sandbox/local.py` | subprocess 实现（命令执行 + 文件读写 + 目录列举） |
| Docker 沙箱 | `sandbox/docker.py` | 容器内执行命令，宿主目录挂载 |
| E2B 沙箱 | `sandbox/e2b.py` | 云端隔离沙箱（需 API Key） |
| 沙箱工厂 | `sandbox/__init__.py` | 按 `SANDBOX_PROVIDER` 分发（local/docker/e2b） |
| 文件工具 | `tools/file.py` | read_file / write_file / list_files |
| 终端工具 | `tools/terminal.py` | run_command（受限命令执行） |
| Git 工具 | `tools/git.py` | git_status / git_diff / git_commit |
| 工具集合 | `tools/__init__.py` | `get_tools()` 聚合 7 个工具 |

### 3.4 多 Agent 编排（P2）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| Coding Agent | `agents/coding.py` | ReAct 单 Agent 闭环（LangGraph create_react_agent） |
| Planner Agent | `agents/planner.py` | 任务拆解为 JSON 步骤列表 |
| Testing Agent | `agents/testing.py` | 沙箱运行测试命令 |
| Review Agent | `agents/review.py` | LLM 审查代码 diff |
| Orchestrator | `agents/orchestrator.py` | LangGraph StateGraph：Planner→Coding→Testing⇄Coding→Review |
| 状态机 | `agents/state.py` | `TaskStatus` 枚举 + 转移表 + `AgentState` |
| 数据库连接 | `db/session.py` | SQLAlchemy engine + `Base` + `get_db` + `init_db` |
| ORM 模型 | `models/task.py` | `Task`(task_id/prompt/status/steps) / `Execution` / `TaskStatus` |

### 3.5 代码检索与评测（P3）

| 模块 | 文件 | 说明 |
| --- | --- | --- |
| 语法分块 | `rag/chunker.py` | 按顶层 class/def 边界切分，保留语法完整性 |
| 关键词检索 | `rag/bm25.py` | 标准 BM25 实现（无外部依赖） |
| 混合检索 | `rag/retriever.py` | `CodeRetriever`，向量检索接口预留 |
| 评测指标 | `rag/eval.py` | Recall@k / MRR |

### 3.6 前端（frontend/）

| 页面 | 文件 | 说明 |
| --- | --- | --- |
| 布局 | `src/app/layout.tsx` | 顶部导航（Dashboard / Agent Chat） |
| Dashboard | `src/app/page.tsx` | 创建任务 + 任务列表 |
| Agent Chat | `src/app/chat/page.tsx` | 对话式交互（流式响应预留） |
| Task Timeline | `src/app/tasks/[id]/page.tsx` | 任务步骤时间线（轮询状态直至完成） |
| API 客户端 | `src/lib/api.ts` | 后端接口封装 + 类型定义 |

### 3.7 测试（backend/tests/）

- `test_sandbox.py`：沙箱命令执行 / 文件读写
- `test_tools.py`：文件 / 终端 / Git 工具
- `test_state.py`：状态机转移
- `test_chunker.py`：代码分块
- `test_retriever.py`：代码检索
- `test_eval.py`：评测指标

---

## 4. 待实现 / 技术债

| 项 | 说明 | 优先级 |
| --- | --- | --- |
| pgvector 向量检索 | 检索目前仅 BM25，向量检索 + 混合重排待接入 | 高 |
| 真实 LLM 编排 | 无 API Key 时走 mock 模式，配置 key 后走 LangGraph 编排 | 中 |
| 流式响应（SSE） | Chat 页面流式输出预留，未对接 Agent | 中 |
| 人工审批（interrupt） | LangGraph Human-in-the-loop 未接入 | 中 |
| 评测集数据 | 指标函数已就绪，缺真实评测集与解决率报告 | 中 |
| Celery 异步任务 | worker 已配置，API 当前用线程执行器，未接入分布式队列 | 中 |
| next 安全升级 | 需升级至 next 16 + React 19（breaking change） | 低 |

---

## 5. 当前可运行能力

默认使用 SQLite + 本地沙箱，**无需 Docker** 即可跑通。配置 LLM API Key 后走真实多 Agent 编排（支持 OpenAI / DeepSeek / Claude），否则走 mock 模式；沙箱可切换 Docker / E2B。

> 详细分步操作见 [本地环境安装与运行步骤](./local-setup.md)。

```powershell
# 1. 后端（26 测试已通过，首次启动自动建表）
cd backend
uv sync
uv run pytest -q
uv run uvicorn app.main:app --reload
# GET /health → {"status":"ok"}
# POST /api/v1/tasks → 创建任务（后台执行，含步骤流转）
# GET /api/v1/tasks/{task_id} → 查询任务状态

# 2. 前端（类型检查与构建已通过）
cd frontend
npm install
npx tsc --noEmit
npm run dev
# http://localhost:3000 → Dashboard（创建任务 + 列表）
# http://localhost:3000/tasks/[id] → 任务步骤时间线（自动轮询）
# http://localhost:3000/chat → Agent Chat

# 可选：生产环境使用 PostgreSQL + Redis
docker compose up -d
```

---

## 6. 下一步计划

1. 接入 pgvector 向量检索，完善混合检索
2. 接入 Celery 分布式队列（替换当前线程执行器）
3. 构建评测集，产出量化解决率报告
4. 前端流式响应与人工审批交互

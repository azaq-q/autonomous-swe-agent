# 本地环境安装与运行步骤

> 本文档面向从零开始的本地开发环境搭建，按步骤操作即可把整个项目跑起来。
>
> 默认使用 **SQLite + 本地沙箱**，无需 Docker、无需 LLM API Key 即可跑通核心闭环。
> 需要真实多 Agent 编排时，再按「可选步骤」配置 LLM Key。

---

## 0. 环境要求总览

| 工具 | 版本要求 | 用途 |
| --- | --- | --- |
| Python | 3.12 | 后端运行时 |
| uv | 最新版 | Python 依赖与虚拟环境管理 |
| Node.js | ≥ 18.17（建议 20/22 LTS） | 前端运行时 |
| npm | 随 Node 附带 | 前端依赖管理 |
| Git | 任意 | 克隆仓库 |
| Docker（可选） | 最新版 | 仅生产/完整环境（PostgreSQL + Redis） |

> Windows 用户全程使用 **PowerShell**（本文命令均按 PowerShell 编写）。

---

## 1. 安装基础工具

### 1.1 安装 Python 3.12

1. 打开官网 <https://www.python.org/downloads/> 下载 3.12 安装包。
2. 安装时务必勾选 **Add Python to PATH**。
3. 验证：

```powershell
python --version
# 期望输出：Python 3.12.x
```

### 1.2 安装 uv

```powershell
# 方式一（推荐）：winget
winget install --id=astral-sh.uv -e

# 方式二：pip
pip install uv
```

验证：

```powershell
uv --version
```

### 1.3 安装 Node.js（含 npm）

1. 打开 <https://nodejs.org/> 下载 **LTS 版本**（20 或 22）。
2. 默认安装即可（会自动加入 PATH）。
3. 验证：

```powershell
node --version   # 期望 ≥ v18.17.0
npm --version
```

---

## 2. 获取代码

```powershell
git clone <你的仓库地址> autonomous-swe-agent
cd autonomous-swe-agent
```

---

## 3. 配置后端

### 3.1 创建 `.env`（可选，默认即可跑通）

后端默认配置已经能跑（SQLite + 本地沙箱）。如需自定义或配置 LLM，复制示例文件：

```powershell
cd backend
Copy-Item .env.example .env
```

`.env` 关键配置说明：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./swe_agent.db` | 数据库地址，本地默认 SQLite |
| `SANDBOX_PROVIDER` | `local` | 沙箱类型，本地用 `local` |
| `OPENAI_API_KEY` | 空 | 填了则走 OpenAI 真实编排 |
| `ANTHROPIC_API_KEY` | 空 | 填了则走 Anthropic 真实编排 |
| `DEFAULT_MODEL` | `gpt-4o` | 模型名，需与所选 provider 匹配 |
| `REDIS_URL` | `redis://localhost:6379/0` | 本地默认模式用不到 |

> 不配置任何 API Key 时，任务会走 **mock 模式**（模拟步骤流转），不影响功能验证。

---

## 4. 安装并启动后端

在 `backend` 目录下执行：

```powershell
# 安装依赖（uv 自动创建 .venv 并锁定版本）
uv sync
```

可选：先跑一遍单元测试确认环境正常（26 个测试）。

```powershell
uv run pytest -q
# 期望输出：26 passed
```

启动后端服务：

```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

看到下面输出即启动成功：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

验证接口：

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/health
# 期望输出：status  ok
```

> 首次启动会自动创建 SQLite 表（`backend/swe_agent.db`）。

---

## 5. 安装并启动前端

新开一个终端，进入 `frontend` 目录：

```powershell
cd ../frontend
npm install
```

可选：配置后端地址（默认就是 `http://localhost:8000`，一般无需改）。

```powershell
# 仅在后端端口不是 8000 时才需要
Copy-Item .env.example .env.local
# 编辑 .env.local 里的 NEXT_PUBLIC_API_BASE_URL
```

启动前端开发服务器：

```powershell
npm run dev
```

浏览器访问：

| 页面 | 地址 | 说明 |
| --- | --- | --- |
| Dashboard | http://localhost:3000 | 创建任务 + 任务列表 |
| Agent Chat | http://localhost:3000/chat | 对话式交互 |
| 任务时间线 | http://localhost:3000/tasks/任务ID | 自动轮询步骤状态 |

---

## 6. 端到端验证

保持后端 + 前端同时运行。

### 6.1 用命令验证后端闭环

```powershell
# 1) 创建任务
$body = @{ prompt = "给项目添加一个 hello 函数" } | ConvertTo-Json
$task = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/tasks -Method Post -ContentType "application/json" -Body $body
$task.task_id   # 记下这个 task_id

# 2) 查询任务状态（等待几秒后查询，会看到 steps 逐步 done，status 变为 done）
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/tasks/$($task.task_id)
```

### 6.2 在浏览器里验证

1. 打开 http://localhost:3000
2. 输入任务描述，点击「创建任务」
3. 自动跳转到任务时间线页，能看到 5 个步骤逐步从 `pending` → `running` → `done`。

---

## 7. 可选：接入真实 LLM 编排

编辑 `backend/.env`，填入 API Key 后重启后端即可（无需改代码）。

**OpenAI：**

```env
OPENAI_API_KEY=sk-xxxx
DEFAULT_MODEL=gpt-4o
```

**DeepSeek（走 OpenAI 兼容接口）：**

```env
OPENAI_API_KEY=sk-<你的 DeepSeek Key>
OPENAI_BASE_URL=https://api.deepseek.com/v1
DEFAULT_MODEL=deepseek-chat
```

> DeepSeek 模型名：`deepseek-chat`（V3）或 `deepseek-reasoner`（R1）。

**Anthropic（Claude）：**

```env
ANTHROPIC_API_KEY=sk-ant-xxxx
DEFAULT_MODEL=claude-3-5-sonnet-latest
```

> 注意：`DEFAULT_MODEL` 必须与填写的 provider 匹配（`gpt-*`/`deepseek-*` 用 OpenAI 兼容通道，`claude-*` 用 Anthropic）。

---

## 8. 可选：切换沙箱（Docker / E2B）

默认沙箱是**本地 subprocess**（`SANDBOX_PROVIDER=local`），无需额外依赖。如需隔离执行，可切换到 Docker 或 E2B。

**Docker 沙箱（本机容器隔离）：**

1. 启动 Docker Desktop，确认 `docker ps` 能跑通。
2. 安装 docker SDK：

```powershell
cd backend
uv add docker
```

3. 编辑 `backend/.env`：

```env
SANDBOX_PROVIDER=docker
DOCKER_IMAGE=python:3.12-slim
```

**E2B 沙箱（云端隔离，需要 API Key）：**

1. 在 <https://e2b.dev> 注册并获取 `E2B_API_KEY`。
2. 安装 e2b SDK：

```powershell
cd backend
uv add e2b
```

3. 编辑 `backend/.env`：

```env
SANDBOX_PROVIDER=e2b
E2B_API_KEY=e2b_xxxx
E2B_TEMPLATE=base
```

> 重启后端后生效。切换后 Agent 的文件读写与命令执行都会在对应沙箱内完成。

---

## 9. 可选：生产环境（PostgreSQL + Redis + pgvector）

本地开发用不到，如需完整生产环境：

```powershell
docker compose up -d
```

然后把 `backend/.env` 里的数据库地址改为：

```env
DATABASE_URL=postgresql+psycopg://swe:swe@localhost:5432/swe_agent
REDIS_URL=redis://localhost:6379/0
```

---

## 10. 常见问题排查

### 10.1 端口被占用

- 后端 8000 被占用：改 `--port 8001`，同时前端 `.env.local` 里改 `NEXT_PUBLIC_API_BASE_URL`。
- 前端 3000 被占用：`npm run dev -- -p 3001`。

### 10.2 前端连不上后端 / 浏览器报 CORS 错误

- 确认后端在 8000 端口运行，且 `GET /health` 能通。
- 后端已开启 CORS，允许 `localhost:3000` 跨域；若前端换了端口，需要同步修改后端 `app/main.py` 里的 `allow_origins`。

### 10.3 `uv` 命令找不到

- 确认已安装 uv 并加入 PATH，重新打开终端再试。

### 10.4 Node 版本过低

- Next.js 14 要求 Node ≥ 18.17，升级到 LTS 版本后重试 `npm install`。

### 10.5 数据库文件在哪

- SQLite 文件生成在 `backend/swe_agent.db`，删除后重启后端会自动重建空库。

### 10.6 沙箱工作目录在哪

- 本地沙箱在 `backend/workspace/`，Agent 的文件读写与命令执行都在该目录下。

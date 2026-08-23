# Autonomous SWE Agent 产品设计文档

## 1. 项目概述

### 项目名称

Autonomous SWE Agent

### 项目定位

一个面向软件工程任务的自主 AI Agent 平台。

用户可以输入自然语言形式的软件开发任务，例如：

> 修复 GitHub Issue #123：用户登录后 Token 过期导致无法刷新

Agent 会自动完成：

1. 理解需求
2. 分析代码仓库
3. 定位问题
4. 制定修改方案
5. 修改代码
6. 执行测试
7. 生成变更说明
8. 创建 Pull Request

### 项目目标

打造类似：

* GitHub Copilot Agent
* Devin
* OpenAI Codex Agent

的工程化 AI 软件开发助手。

核心目标：

> 让 AI Agent 具备完整的软件工程闭环能力，而不仅是代码生成能力。

---

# 2. 用户场景

## 场景一：自动修复 Bug

用户：

```
Fix issue #456:
The payment API returns 500 error when coupon is expired.
```

Agent：

```
1. Clone repository

2. Analyze payment service

3. Find coupon validation logic

4. Identify exception handling bug

5. Modify code

6. Run unit tests

7. Generate PR
```

---

## 场景二：实现新功能

用户：

```
Add OAuth login support with Google.
```

Agent：

自动：

* 分析项目架构
* 查找认证模块
* 设计修改方案
* 添加代码
* 编写测试

---

## 场景三：代码 Review

用户：

```
Review this Pull Request
```

Agent：

输出：

* Bug 风险
* 性能问题
* 安全问题
* 可维护性建议

---

# 3. 产品架构

整体架构：

```
                 User

                  |
                  |

              Web UI

                  |
                  |

             API Gateway

                  |
                  |

          Agent Orchestrator

                  |
 ------------------------------------------------
 |              |              |                 |
Planner      Coding Agent   Testing Agent   Review Agent

                  |

              Tool Layer

 ------------------------------------------------
 |              |              |                 |

Git Tool    Code Search    Terminal      Browser

                  |

             Execution Sandbox

                  |

              Repository
```

---

# 4. Agent 系统设计

## 4.1 Agent Orchestrator

负责：

* 任务拆解
* Agent 调度
* 状态管理
* 错误恢复

技术：

* LangGraph
* OpenAI Agents SDK
* Temporal

任务状态：

```json
{
  "task_id": "123",
  "status": "running",
  "current_step": "testing",
  "repository": "github/project"
}
```

---

# 5. Multi-Agent Design

## 5.1 Planner Agent

职责：

理解用户需求并生成执行计划。

输入：

```
Fix login bug
```

输出：

```json
{
 "steps":[
   "Analyze authentication module",
   "Find token refresh logic",
   "Modify implementation",
   "Run tests"
 ]
}
```

---

## 5.2 Code Agent

职责：

负责：

* 阅读代码
* 生成 Patch
* 修改文件

能力：

* Repository understanding
* Code generation
* Refactoring

---

## 5.3 Research Agent

职责：

搜索：

* 项目文档
* Github issue
* API 文档

工具：

* GitHub API
* Web Search
* Vector Search

---

## 5.4 Testing Agent

职责：

自动验证代码。

能力：

* 运行测试
* 分析失败日志
* 修复测试问题

---

## 5.5 Review Agent

职责：

模拟人工 Code Review。

检查：

* Bug
* Security
* Performance
* Code Style

---

# 6. 核心技术设计

# 6.1 Repository Understanding

问题：

大型项目无法一次输入 LLM。

解决：

建立代码知识库。

Pipeline：

```
Repository

↓

Parser

↓

Chunk Code

↓

Generate Embedding

↓

Vector Database

↓

Semantic Search

↓

LLM Context
```

技术：

* Tree-sitter
* Chroma
* Milvus
* PostgreSQL pgvector

---

# 6.2 Code Search System

支持：

自然语言搜索：

```
Where is authentication handled?
```

返回：

```
auth/service/token.py

class TokenManager:
    refresh_token()
```

---

# 6.3 Memory System

Agent Memory：

短期：

```
Current task state
```

长期：

```
Repository knowledge
Previous fixes
Coding style
```

存储：

* Redis
* PostgreSQL

---

# 7. Tool System

## Git Tool

能力：

```
clone repository

create branch

commit

push

create PR
```

---

## Terminal Tool

执行：

```
npm test

pytest

mvn test
```

必须运行在：

Docker Sandbox

---

## File Tool

能力：

```
read file

write file

search file

diff file
```

---

# 8. Sandbox 安全设计

Agent 生成代码具有风险。

采用：

```
Agent

 |

Docker Container

 |

Limited Permission

 |

Execution
```

限制：

* CPU
* Memory
* Network
* File Permission

---

# 9. 数据库设计

## User

```sql
user
----
id
email
created_at
```

## Repository

```sql
repository
----
id
user_id
github_url
language
```

## Task

```sql
task
----
id
repository_id
prompt
status
created_at
```

## Agent Execution

```sql
execution
----
id
task_id
agent_name
input
output
timestamp
```

---

# 10. 前端设计

技术：

* Next.js
* TypeScript
* TailwindCSS

页面：

## Dashboard

展示：

```
Projects

Active Tasks

Completed PR
```

---

## Agent Chat

类似：

Cursor / ChatGPT。

支持：

* Streaming Response
* Code Preview
* Diff View

---

## Task Timeline

展示：

```
✓ Analyze Repository

✓ Locate Bug

✓ Modify Code

✓ Run Tests

○ Create PR
```

---

# 11. 后端设计

技术：

## API

FastAPI

## Task Queue

Celery / Redis

## Database

PostgreSQL

## Cache

Redis

## LLM

支持：

* GPT
* Claude
* Gemini

---

# 12. 系统流程

完整流程：

```
User Request

↓

Task Parser

↓

Planner Agent

↓

Repository Analysis

↓

Code Agent

↓

Generate Patch

↓

Testing Agent

↓

Review Agent

↓

Human Approval

↓

Create PR
```

---

# 13. MVP 版本规划

## Phase 1（2周）

基础 Agent：

完成：

* GitHub 登录
* Repo Clone
* Chat Interface
* Code Search

---

## Phase 2（3周）

代码修改能力：

完成：

* File Modification
* Patch Generation
* Docker Execution

---

## Phase 3（2周）

工程化：

完成：

* Test Agent
* Review Agent
* PR Creation

---

# 14. 高级 Feature

## 14.1 Self Reflection

Agent 自动检查：

```
Did my solution actually fix the issue?
```

---

## 14.2 Multi-model Routing

不同任务调用不同模型：

代码：

Claude/GPT

总结：

Small Model

---

## 14.3 Human Feedback Loop

用户评价：

```
Accept

Reject

Modify
```

用于优化 Agent。

---

# 15. 简历描述

## 项目标题

Autonomous SWE Agent — AI Software Engineering Assistant

## Resume Bullet

* Designed and implemented an autonomous software engineering agent capable of analyzing GitHub repositories, generating code patches, executing tests in isolated Docker environments, and creating pull requests through multi-agent orchestration.

* Built a LangGraph-based agent workflow integrating planning, coding, testing, and review agents with tool calling, repository retrieval, and long-term memory.

* Developed a secure sandbox execution system for automated code validation with container isolation, resource limitation, and test feedback loops.

* Implemented a repository-aware RAG pipeline using code parsing, embeddings, and vector search to enable semantic code understanding across large-scale projects.

---

# 16. 面试可展示亮点

该项目可以覆盖：

## AI Engineering

* Agent Architecture
* Tool Calling
* RAG
* Memory
* Evaluation

## Backend Engineering

* Distributed Task Queue
* API Design
* Database
* Streaming

## System Design

* Sandbox
* Scalability
* Reliability
* Security

最终目标：

> 构建一个具备真实软件工程能力的 Autonomous AI Developer。

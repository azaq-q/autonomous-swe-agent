# Autonomous SWE Agent 实现路线对比

> 基于 [autonomous-swe-agent.md](./autonomous-swe-agent.md) 的产品设计文档，梳理可选的实现路线并进行横向比较，辅助技术决策。

## 1. 评估维度

在比较前，先明确衡量每条路线的标准：

| 维度 | 说明 |
| --- | --- |
| 实现周期 | 从 0 到可运行 MVP 所需投入 |
| 技术门槛 | 对开发者工程/AI 能力的要求 |
| 学习/求职价值 | 对个人成长与面试亮点的贡献 |
| 产品差异化 | 是否形成自己的核心能力，而非拼装 |
| 可控性 | 对底层逻辑的掌控与可定制程度 |
| 可维护性 | 依赖收敛、升级成本、代码理解成本 |
| 核心风险 | 该路线最可能翻车的地方 |
| 目标定位 | 最适合的场景（商业验证 / 求职 / 深入学习） |

---

## 2. 四条实现路线

### 路线 A：开源 SWE Agent 二次开发

以成熟开源项目为底座（Fork 或深度集成），聚焦「产品化」。

**候选底座：**

| 项目 | 特点 |
| --- | --- |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | 最接近本项目定位的全栈自主 SWE Agent，自带 UI、Agent Loop、Sandbox、多模型 |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | 学术风、工具化 ACI（Agent-Computer Interface），适合修 Bug 类任务 |
| [Aider](https://github.com/Aider-AI/aider) | CLI 结对编程，代码生成/编辑能力成熟 |
| [Cline](https://github.com/cline/cline) | VS Code 插件形态，Agent 工具链完整 |

**做法：**

```
Fork OpenHands
   ↓
裁剪/改造核心 Agent Loop
   ↓
补齐自己的 Web UI、登录、多租户、任务管理
   ↓
替换模型路由 + 数据存储
```

**优点：** 周期短、功能起点高（工具、Sandbox、Agent Loop 均已有）；能快速验证产品形态。

**缺点：** 代码量大、吃透成本高；差异化弱；受上游演进牵制；对「多 Agent 编排、RAG、Memory」等面试核心点的理解停留在「用过」。

---

### 路线 B：框架编排 + 现成组件（推荐）

以成熟编排框架为核心，自研业务逻辑，基础设施借用 SaaS/开源组件。

**技术栈映射：**

| 设计文档模块 | 选型 |
| --- | --- |
| Agent Orchestrator | LangGraph（或 OpenAI Agents SDK） |
| 多 Agent 协作 | LangGraph StateGraph + 子图 |
| Repository Understanding | tree-sitter 解析 + Chroma/pgvector 向量库 |
| Tool Calling | 自研 File/Git/Terminal 工具 + Composio（可选） |
| Execution Sandbox | E2B / Docker + gVisor（自制也行） |
| Memory | Redis（短期）+ PostgreSQL（长期） |
| 后端 | FastAPI + Celery/Redis |
| 前端 | Next.js + TypeScript + TailwindCSS |
| LLM | GPT / Claude / Gemini 多模型路由 |

**做法：**

```
自研 Planner/Code/Test/Review Agent 的 Prompt 与状态机
   ↓
用 LangGraph 编排多 Agent 依赖与回退
   ↓
工具层：自研 Git/File/Terminal + 语义检索
   ↓
Sandbox：优先 E2B，节省运维成本
```

**优点：** 平衡速度与可控性；技术栈主流，简历含金量高；核心逻辑（Planning、Agent 协作、工具调用、RAG、Memory、Eval）均为自研，可深度讲解。

**缺点：** 仍有大量 glue code；框架版本演进需跟进；需要清晰的边界设计，避免「框架绑架」。

---

### 路线 C：从零全自研

除 LLM API 外，编排、工具、Sandbox、RAG、Memory 全部手写。

**做法：**

```
自研 ReAct/Plan-Execute Agent Loop
   ↓
自研 Tool Calling 协议与工具注册
   ↓
自研 Docker/Firecracker Sandbox 调度
   ↓
自研代码分块 + Embedding + 向量检索
   ↓
自研任务状态机 + 错误恢复
```

**优点：** 深度理解每个环节；可控性与技术深度最大；面试可覆盖 AI Engineering 全链路。

**缺点：** 周期最长、坑最多（可靠性、重试、并发、Sandbox 安全、流式输出）；易陷入细节导致半途而废；对求职者而言「什么都自己写」未必优于「会选型 + 会组合」。

---

### 路线 D：渐进式演进（单 Agent 起步）

不直接搭建完整多 Agent 平台，先做「单 Agent + 工具」的 CLI 闭环，逐步演进。

**演进路径：**

```
Phase 1: 单 Agent + 工具调用（ReAct 循环，跑通「改文件 → 跑测试」）
   ↓
Phase 2: 加 Sandbox 隔离 + Git 工具（clone/branch/commit）
   ↓
Phase 3: 拆分为 Planner/Code/Test 多 Agent
   ↓
Phase 4: 加 RAG 检索 + Memory + Web UI + PR 创建
```

**做法：**

```
MVP 仅一个 Coding Agent
   ↓
用 OpenAI Agents SDK / smolagents 快速串起工具
   ↓
验证价值后，再逐层加编排、检索、UI
```

**优点：** 风险低、反馈快；每一步都能看到可运行成果；适合单人/业余时间推进；最终架构仍可收敛到路线 B。

**缺点：** 前期不算「多 Agent」，与设计文档的完整形态有距离；若目标就是展示完整平台，会显得「没一步到位」。

---

## 3. 多维度对比总表

| 维度 | A 二次开发 | B 框架+组件（推荐） | C 全自研 | D 渐进演进 |
| --- | --- | --- | --- | --- |
| 实现周期 | 短 | 中 | 长 | 中（分阶段） |
| 技术门槛 | 中（读源码） | 中 | 高 | 低→中 |
| 学习/求职价值 | 中 | 高 | 最高 | 中高 |
| 产品差异化 | 弱 | 中 | 强 | 中 |
| 可控性 | 低 | 中高 | 最高 | 高 |
| 可维护性 | 低（依赖上游） | 中高 | 高 | 中高 |
| 核心风险 | 上游绑架、吃不透 | 框架演进、glue code 多 | 周期失控、坑多 | 偏离完整形态 |
| 目标定位 | 快速商业验证 | 求职 + 可落地产品 | 深度理解 + 展示 | 稳健入门 + 逐步完善 |

---

## 4. 与 MVP Phase 规划的映射

设计文档规划了 Phase 1/2/3，各路线落地节奏如下：

| 阶段 | A 二次开发 | B 框架+组件 | C 全自研 | D 渐进演进 |
| --- | --- | --- | --- | --- |
| Phase 1：登录/克隆/聊天/检索 | 大部分已有，改 UI | 用 LangGraph + 组件组装 | 全手写 | 先做单 Agent |
| Phase 2：改文件/Patch/Docker 执行 | 已内置 | 自研工具 + E2B | 自研 Sandbox | 补工具 + Sandbox |
| Phase 3：Test/Review/PR | 改造现有 | 自研 Agent 状态机 | 自研多 Agent | 拆分多 Agent |

---

## 5. 技术选型速查

无论哪条路线，核心依赖建议收敛到以下组合：

- **编排**：LangGraph（图结构、状态管理、人工审批天然契合）或 OpenAI Agents SDK（更轻）
- **Agent 模式**：Planner 用 Plan-and-Execute，Code/Test/Review 用 ReAct + 工具调用
- **检索**：tree-sitter（结构化解析）+ Chroma/pgvector（向量，可复用 PostgreSQL）
- **Sandbox**：E2B（托管、省心）或自建 Docker + gVisor/Firecracker（可控）
- **工具**：Git/File/Terminal 自研（核心壁垒），Web/Search 可用 Composio/Browserbase
- **Memory**：Redis（任务态）+ PostgreSQL（长期知识、execution 记录）
- **模型路由**：复杂推理用 Claude/GPT，总结/分类用小模型

---

## 6. 推荐与决策建议

### 推荐：路线 B（框架编排 + 现成组件），可叠加 D 的渐进节奏

理由：

1. **平衡点最优**：既能在合理周期内做出可运行、可展示的平台，又保留自研核心逻辑，满足求职深度要求。
2. **与设计文档高度契合**：文档明确点名 LangGraph、OpenAI Agents SDK、pgvector、tree-sitter，路线 B 正是把这些「组合起来」而非「从头造」。
3. **风险可控**：编排、工具、RAG、Memory、Eval 这些「可讲、可展示」的部分自己写；Sandbox、向量库等「纯基础设施」用现成组件，避免陷入非核心细节。

### 决策速查

- 目标是**快速上线验证商业可行性** → 选 A（Fork OpenHands）。
- 目标是**求职/面试 + 完整可运行作品** → 选 B。
- 目标是**极致深入学习、吃透每一层** → 选 C。
- 目标是**单人业余、稳健推进、逐步演进** → 选 D。

---

## 7. 落地建议（针对路线 B）

1. 先跑通「单 Agent 改文件 → 跑测试」最小闭环，再叠加多 Agent。
2. 优先用 E2B 承接 Sandbox，待核心能力稳定后再评估自建。
3. 把 RAG 检索做在 PostgreSQL(pgvector) 上，减少多一套向量库的运维成本。
4. 预留「人工审批」节点（Human-in-the-loop），LangGraph 的 interrupt 机制可天然支持。
5. 每个 Agent 输出结构化为 JSON，便于状态持久化与 Eval 复现。

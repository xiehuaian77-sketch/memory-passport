# Memory Passport — Hackathon Project Submission

> **项目名称**：Memory Passport (记忆护照)  
> **项目版本**：`v1.10.1-evaluation-platform` (Commit `e68380b0447a58f7925da0ca2cc0a20a72d65496`)  
> **开源仓库**：[https://github.com/xiehuaian77-sketch/memory-passport.git](https://github.com/xiehuaian77-sketch/memory-passport.git)  
> **演示凭据**：  
> - 邮箱演示账户：`demo@memorypassport.ai` / `demo123456`  
> - 演示 Passport ID：`mp_demo_hackathon`  
> - 演示 Web3 钱包：`0x71C2E63B48421882c7aE9D58E16503c403Be43F0`

---

## 一、一句话简介 (One-Sentence Pitch)

**Memory Passport 是专为自主 AI Agent 设计的终身主权长程记忆基础设施，具备双时态演进、冲突智能仲裁、知识图谱展开、透明解释与可量化评测，通过标准 MCP 协议与 Python SDK 让记忆在所有 Agent 间无缝携带与漫游。**

---

## 二、问题与行业痛点 (Problem Statement)

随着大模型生态从单次问答演进为自主 Agent 协同工作流，长程记忆成为行业公认的核心瓶颈：
1. **记忆数据孤岛与厂商锁定 (Memory Fragmentation & Lock-in)**：
   用户的偏好、过往项目经验散落在 ChatGPT、Claude、Cursor、个人 Agent 中，彼此割裂，用户换一个应用就不得不重复“自报家门”。
2. **纯向量检索的“时间盲区”与事实陈旧 (Temporal Blindness & Stale Hallucinations)**：
   传统 Vector DB 只比对语义相似度，对时间演化毫无感知。当用户从“住在北京”搬家到“住在上海”，相似度算法依然会召回“住在北京”，诱发严重幻觉。
3. **事实逻辑冲突缺乏治理机制 (Lack of Conflict Arbitration)**：
   随着对话积累，Agent 内部产生大量互相矛盾的陈述（如配置项变更、日程冲突），现有方案缺乏自动冲突检测与显式版本接替能力。
4. **RAG 检索黑盒与质量不可度量 (Black-Box Retrieval & Unquantified Quality)**：
   开发者无法获知单条记忆被召回的数学权值细节，更缺乏统一的 Golden Dataset 评测体系来量化不同检索策略的有效性。

---

## 三、解决方案与核心特性 (The Solution & Core Features)

Memory Passport 从零自研打造了全栈闭环的长程记忆系统：

### 1. 跨 Agent 主权身份 (Sovereign Passport & Web3 SIWE)
- 采用 **Passport ID** 作为全局主权实体，支持传统邮箱及 **EIP-4361 (Sign-In With Ethereum)** 钱包公私钥签名无密码鉴权。
- 记忆资产归属人类用户本身，支持通过标准协议在任意 Agent（Claude、Cursor、自定义 Agent）间漫游。

### 2. 双时态时序记忆引擎 (Dual-Timeline Temporal Engine)
- 区分**有效时间 (Valid Time)** 与 **事务时间 (Transaction Time)**，精确建模事实在现实世界的生命周期。
- 引入时序半衰期衰减函数：$\text{decay} = 2^{-\Delta t / t_{1/2}}$。
- 显式版本接替链（`SUPERSEDES`），旧记忆优雅过渡为 `SUPERSEDED`，检索层默认自动过滤陈旧事实。

### 3. 冲突智能仲裁与治理 (Conflict Intelligence)
- 写入阶段自动执行语义对撞，定位互斥事实，打标 `CONFLICTED` 并挂载 `CONTRADICTS` 关系边。
- 提供人机协同的冲突解决工作流：一键执行版本升级（Supersede）、允许多样性共存（Coexist）或废弃（Discard）。

### 4. 关系拓扑图谱 (Relationship Graph Layer)
- 在向量点状知识之上构建语义拓扑连接，支持 `SUPERSEDES`、`DERIVED_FROM`、`CONTRADICTS`、`RELEVANT_TO` 强语义关系。
- 具备高效的 **1-Hop 剪枝图遍历机制**，将点对点相似度搜索升级为拓扑上下文扩展搜索。

### 5. 多模态混合检索与透明可解释性 (Hybrid Retrieval & Memory Explain)
- 自研 **Hybrid Engine**：融合 pgvector 余弦相似度、PostgreSQL GIN 倒排索引全文搜索、时间衰减与 Graph Boost。
- **Memory Explain** 审计：毫秒级透视单次检索的 Vector Score、FTS Rank、Temporal Factor 与关系拓扑扩展链路。

### 6. 开源标准接入生态 (Native MCP & Python SDK)
- 原生支持 Anthropic **Model Context Protocol (MCP 2024-11-05)** 标准 Streamable HTTP 端点（`POST /mcp`），内置 15 项标准 Tools。
- 提供独立且类型安全的 Python SDK（`memory_passport`），52/52 单元与集成测试全绿通过。

### 7. 生产级基准评测平台 (Built-in Evaluation Platform)
- 原生内置评测集管理、Golden Dataset 录入与跨实验跑分对撞体系。
- 自动度量 **Recall@K**、**MRR (Mean Reciprocal Rank)**、**Latency (ms)** 与通过率，直观呈现不同策略的技术收益。

---

## 四、系统架构与技术栈 (Architecture & Tech Stack)

```
+--------------------------------------------------------------------+
|                         Client & Ecosystem                         |
|   Claude Desktop / Cursor (MCP) | Python SDK Client | Web Browser  |
+--------------------------------------------------------------------+
                                  |
                                  v
+--------------------------------------------------------------------+
|                     Memory Passport API Layer                      |
|           FastAPI / Pydantic v2 / JWT + EIP-4361 SIWE Auth         |
|              Standard MCP Server (Streamable HTTP & REST)          |
+--------------------------------------------------------------------+
                                  |
                                  v
+--------------------------------------------------------------------+
|                         Core Engine Layer                          |
|  * Temporal Engine (Effective Time, Recency Decay, Supersede Chain)|
|  * Conflict Intelligence (Semantic Detection, Resolution Flow)     |
|  * Relationship Graph (1-Hop BFS, Topology Boost)                  |
|  * Hybrid Retrieval (pgvector Cosine + Postgres FTS + Recency)     |
|  * Evaluation Engine (Golden Dataset, Recall@K, MRR, Latency)      |
|  * Audit & Quality Engine (7-Dimensional Quality Diagnostics)      |
+--------------------------------------------------------------------+
                                  |
                                  v
+--------------------------------------------------------------------+
|                        Data & Storage Tier                         |
|        PostgreSQL 16 + pgvector (HNSW Indexing, GIN FTS)           |
|        9 Alembic Migrations (001 -> 009 Smooth Evolution)          |
+--------------------------------------------------------------------+
```

- **后端架构**：Python 3.11+, FastAPI, SQLAlchemy 2.0 (AsyncIO), pgvector, Alembic
- **前端架构**：Next.js 14 App Router, React, Tailwind CSS, Lucide React, Framer Motion
- **协议标准**：Model Context Protocol (MCP) 2024-11-05 Spec, EIP-4361 SIWE
- **工程指标**：
  - 后端自动化测试套件：**572 passed, 0 failed, 0 errors**
  - Python SDK 测试套件：**52 passed, 0 failed**
  - Ruff 代码规范：**0 violations**
  - TypeScript 类型检查：**0 errors**
  - 数据库迁移版本：**001 至 009 全部验证通过**

---

## 五、评测实验与硬核数据 (Empirical Evaluation Benchmarks)

在 `Developer Profile & Tech Stack Golden Dataset`（5 道标准测试用例）下的真实跨实验对比：

| 评测实验 | 检索策略配置 | Recall@5 | MRR (Mean Reciprocal Rank) | 平均耗时 (Mean Latency) | 测试用例通过率 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Baseline Run** | 仅传统全文关键词检索 (Keyword FTS) | **0.8000** | **0.5400** | **2.35 ms** | 80% (4/5 passed) |
| **Enhanced Hybrid Run** | 向量 + 全文 + 1-Hop图扩展 + 时序过滤 | **1.0000** | **0.4567** | **16.74 ms** | **100% (5/5 passed)** |

### 核心收益分析：
1. **召回率质的飞跃 (Recall 0.80 -> 1.00)**：基线检索对语义相关但措辞不同的查询（如“项目采用什么高吞吐异步后端？”）产生漏召回（Recall 为 0）；Enhanced 策略借助向量语义与图谱拓扑实现 **100% 全量命中**。
2. **上下文丰富度与排序平衡 (MRR 0.54 vs 0.4567)**：Enhanced 策略通过图谱展开拉取了关键的先验背景节点，这些拓扑上下文进入了 Top-2，使得单一黄金记忆排名稍有下移，但赋予了 Agent 显著更加全面与坚实的事实上下文。
3. **健康度评分**：Memory Quality 引擎基于 7 个维度（置信度、重要性、新鲜度、一致性、溯源性、去重度、冲突风险）得出综合健康度得分 **0.958**。

---

## 六、安全、隐私与多租户 (Security & Data Sovereignty)

1. **行级隔离机制**：全表强校验 `passport_id` 与 `user_id` 复合索引，DAO 级强制上下文约束，彻底防御横向越权。
2. **不可篡改审计追踪**：每次记忆创建、演化、接替或废弃均同步追加写入只读审计日志表（`MemoryAuditLog`）。
3. **主权凭据自治**：支持 Web3 签名绑定，密钥由用户自主掌握，随时可全量打包导出记忆资产。

---

## 七、未来规划与路线图 (Future Roadmap)

1. **去中心化持久化存储**：集成 IPFS / Filecoin / Arweave，支持用户记忆快照链上锚定与去中心化存证。
2. **联邦记忆网络 (Federated Memory Network)**：支持不同用户所有的多 Agent 在受控访问权限下进行匿名化知识共享。
3. **云原生 Helm Chart 与轻量边缘包**：提供边缘端（如本地 Ollama + 嵌入式 SQLite-vec）单二元包形态，打造更轻量、零依赖的个人记忆小盒子。

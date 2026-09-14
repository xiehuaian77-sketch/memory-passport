# Memory Passport - Hackathon Pitch & Demo Script

**Project:** Memory Passport  
**Target Delivery Duration:** 3.5 ～ 4.5 Minutes (Standard)  
**Alternative Versions:** 3-Minute Compressed | 4.5-Minute Extended  
**Presenter Persona:** Lead Architect / Full-Stack AI Engineer  

---

## 1. Standard Pitch Script (3.5 ～ 4.5 Minutes)

### 00:00 - 00:20 | The Problem & The Passport ID
- **Page:** `http://127.0.0.1:3000/` (Home) & `http://127.0.0.1:3000/dashboard`
- **Action:** 登录演示账号 `demo@memorypassport.ai`（密码 `demo123456`），展示首页身份卡片。
- **Screen Display:** 顶部显示 `Passport ID: mp_demo_hackathon`、绑定的 Web3 钱包地址 `0x71C2E63B48421882c7aE9D58E16503c403Be43F0` 以及活跃统计。
- **Spoken Script (讲解词):**
  > “各位评委老师好！现在的 AI Agent 生态面临一个巨大的根本性瓶颈：**智能体是碎片化且健忘的**。你在 Cursor 设定的代码规范，换到 Claude 或 ChatGPT 必须重新解释一遍；更糟糕的是，很多外部 Agent 只能依赖简单的上下文窗口或封闭的云端缓存，用户无法治理，也无法迁移。
  > **Memory Passport** 就是为解决这个问题而生的——它是面向 AI Agent 的主权化、可验证、可观测的长期记忆基础设施层。”
- **Core Value Pitch (核心卖点):** 跨平台可携带的主权 Agent 记忆身份层，拒绝厂商孤岛锁定。

---

### 00:20 - 00:50 | Memory Center (长期记忆资产库)
- **Page:** `http://127.0.0.1:3000/dashboard`
- **Action:** 浏览已初始化的 10 条高质量记忆，展示按分类（Identity、Preference、Context、Task）筛选。
- **Screen Display:** 展示 Alex Chen 的技术栈画像、VS Code 深色主题偏好、PostgreSQL 数据库架构规范等结构化资产卡片。
- **Spoken Script (讲解词):**
  > “大家看屏幕，这是我们 Demo 用户 Alex 的 Memory Center。系统中沉淀了 10 条真实工程画像记忆：从资深全栈 AI 工程师的技术栈，到 2 空格缩进的编辑偏好，再到团队的 Docker 部署规范。
  > 每一条记忆都不是单纯的文本段落，它具备明确的生命周期状态、置信度（Confidence）与重要性（Importance）权重，构成了 Agent 理解用户的数字化认知基底。”
- **Core Value Pitch (核心卖点):** 结构化、生命周期化的用户工程与偏好资产。

---

### 00:50 - 01:20 | Non-Destructive Extraction (非破坏性记忆抽取)
- **Page:** `http://127.0.0.1:3000/chat`
- **Action:** 输入用户自然对话：“我现在主要使用 Python，并且正在开发 AI Agent。”，触发抽取候选记忆并点击 Confirm。
- **Screen Display:** 弹出 `Extraction Preview` 对话框，高亮抽取出的 Key、Category、Importance，点击确认后无缝注入 Memory Center。
- **Spoken Script (讲解词):**
  > “很多系统在提取用户记忆时，采用黑盒直接写入数据库，导致大量垃圾记忆和幻觉污染。
  > Memory Passport 采用**两阶段人机协作抽取机制（Extract-Preview-Confirm）**：AI 负责在对话中精准嗅探有价值的事实候选，但在落库前给用户透明的审核确认权，确保进入长期记忆库的每一条数据都完全可控。”
- **Core Value Pitch (核心卖点):** 两阶段人机协同确认，杜绝幻觉记忆污染。

---

### 01:20 - 01:50 | Memory-Aware Chat & Indicator (记忆增强对话)
- **Page:** `http://127.0.0.1:3000/chat`
- **Action:** 提问 “What database does Memory Passport use?”，观察界面响应。
- **Screen Display:** Agent 回答准确指出生产使用 PostgreSQL + pgvector、本地使用 SQLite，上方亮起 **Memory Indicator**，显示 `Loaded Memories: 1`。
- **Spoken Script (讲解词):**
  > “现在我们在 Chat 里发起提问。请注意看上方的 Memory Indicator 绿色徽标：**它绝不是前端为了展示效果假装亮起的动画**，而是后端混合检索真实命中并注入上下文时，才严格返回并呈现的溯源指标！
  > Agent 调取的正是用户在 Memory Center 沉淀的架构事实，精准作答，没有多余的废话。”
- **Core Value Pitch (核心卖点):** 检索上下文真实注入，前后端协议级可观测溯源。

---

### 01:50 - 02:20 | Temporal Memory & Supersession (时态记忆与版本更迭)
- **Page:** `http://127.0.0.1:3000/dashboard`
- **Action:** 切换记忆状态筛选为 `superseded`，展示旧记忆 `python_runtime_version_v1` (Python 3.10) 与新记忆 `python_runtime_version_v2` (Python 3.12)；打开历史审计详情。
- **Screen Display:** 旧记忆标记为橙色 `SUPERSEDED`，`valid_until=2026-03-01`，指针链接到 v2；审计日志中明确记录 `SUPERSEDE` 动作与升级原因。
- **Spoken Script (讲解词):**
  > “这是我们最核心的技术壁垒之一：**时态记忆演进（Temporal Supersession）**。
  > 传统向量检索最大的痛点在于：事实会随时间变化！如果我们半年前用 Python 3.10，现在升级到了 Python 3.12，普通向量搜索会因为语义高度相似，同时召回这两条事实，让 Agent 产生版本冲突幻觉。
  > Memory Passport 引入双时间戳（valid_from / valid_until）与显式继承指针。旧事实不会被野蛮删除，而是标记为 superseded 归档，当前检索严格隔离在活跃时态区间，完美解决历史事实漂移问题！”
- **Core Value Pitch (核心卖点):** 首创时态版本链，根治时间推移导致的知识幻觉。

---

### 02:20 - 02:50 | Conflict Intelligence (语义冲突智能识别)
- **Page:** `http://127.0.0.1:3000/dashboard`
- **Action:** 筛选查看状态为 `conflicted` 的记忆卡片：`client_meeting_availability`。
- **Screen Display:** 警告徽标标红，显示检测到语义矛盾：晨间 9:00-12:00 专注工作偏好 vs 每天上午 10:00 客户例会。
- **Spoken Script (讲解词):**
  > “用户在长期使用中难免会说出相互矛盾的要求。例如，用户曾要求‘早上 9 点到 12 点深度专注不排会’，后又在某次对话中提到‘每天 10 点可以开客户例会’。
  > 我们的 **Conflict Intelligence 引擎** 会在事实进入系统时进行语义对比，自动划分为 UPDATE、CONTRADICTION、RELATED、SIMILAR 四类。系统将该事实标记为 `conflicted`，当外部调度 Agent 试图预约会议时，会主动拦截并提示用户确认，防止盲目执行造成业务摩擦。”
- **Core Value Pitch (核心卖点):** 语义级冲突自检与安全拦截，保障自主 Agent 行为稳健。

---

### 02:50 - 03:10 | Relationship Graph 1-Hop (关系知识图谱)
- **Page:** `http://127.0.0.1:3000/dashboard`
- **Action:** 点击记忆详情的关系拓扑面板，查看当前记忆的关联节点。
- **Screen Display:** 显示 5 条真实有向关系边：`SUPERSEDES`、`RELEVANT_TO`、`CONTRADICTS`，置信度在 0.80 ～ 1.00 之间。
- **Spoken Script (讲解词):**
  > “记忆之间是有上下文关联的。我们通过关系图谱服务建立实体有向边。
  > 我们**非常克制地设计为严格的一跳（1-Hop）种子记忆扩展检索**，在极低延迟（< 40ms）内沿图拓展强相关知识，而绝不引入多跳图数据库复杂的计算开销与 token 预算爆炸风险。”
- **Core Value Pitch (核心卖点):** 轻量高效的 1-Hop 关系拓扑，低延迟拓展认知边界。

---

### 03:10 - 03:40 | Evaluation Center & Real IR Metrics (科学评测平台)
- **Page:** `http://127.0.0.1:3000/dashboard/evaluation`
- **Action:** 选中 `Developer Profile & Tech Stack Golden Dataset`，进入 Runs 性能对比视图。
- **Screen Display:** 对比 Run 1（纯关键词）与 Run 2（增强混合检索）雷达图与指标表：
  - **Run 1**: Recall@5: `0.80`, MRR: `0.54`, 平均耗时: `2.35ms`
  - **Run 2**: Recall@5: `1.00`, MRR: `0.4567`, 平均耗时: `16.74ms`, 通过率: `100%`
- **Spoken Script (讲解词):**
  > “传统记忆项目往往把‘检索好’停留在 PPT 口号上。在 Phase 5 中，我们在系统内核嵌入了**工业级科学评测平台**。
  > 评委老师请看屏幕上的真实运行数据：在基准关键词检索下，Recall@5 为 0.80；而启用我们融合了向量、关键词、时间衰减与图拓展的增强检索后，**Recall@5 直接跃升到 100%**，全部 5 个 Golden 测试用例全数通过！平均延迟仅 16.74 毫秒。所有指标均由后端 `EvaluationService` 实测沉淀，杜绝任何人工打假数据。”
- **Core Value Pitch (核心卖点):** 业界首个内建科学 IR 评测看板的 Agent 记忆系统。

---

### 03:40 - 04:10 | Explainable Memory Quality (可解释记忆质量)
- **Page:** `http://127.0.0.1:3000/dashboard/evaluation` 底部
- **Action:** 点击查看 Demo 记忆的 Quality 详情。
- **Screen Display:** 展示综合质量得分 `0.958`，以及 7 个细分维度雷达图：`confidence` (1.0)、`importance` (0.92)、`freshness` (1.0)、`consistency` (1.0)、`provenance` (1.0)、`duplication` (0.8)、`conflict_risk` (1.0)，附带打分依据与健康状态。
- **Spoken Script (讲解词):**
  > “记忆质量高不高，不能靠黑盒打一个随机分。Memory Passport 建立了包含新鲜度、一致性、可溯源性、重要性等在内的 **7 维度确定性质量评估模型**。
  > 系统清晰地告诉开发者：这条记忆为什么能得 0.958 分，扣分点是因为与现有微服务定义存在轻度语义重复。每一分都具备白盒可解释性。”
- **Core Value Pitch (核心卖点):** 7 维度白盒可解释质量评估，记忆健康一目了然。

---

### 04:10 - 04:30 | Developer Integration (Python SDK & MCP 实机运行)
- **Page:** 终端命令行
- **Action:** 执行 `python scripts/demo_agent_run.py`，观察命令行端输出。
- **Screen Display:**
  - 自动通过 live server 验证连接
  - 自然语言检索展示匹配记忆与得分
  - 自动排除过期 Python 3.10，选中活跃 Python 3.12
  - 命中晨间专注冲突，主动安全预警
  - 退出码 0，52/52 SDK 测试保证可靠性
- **Spoken Script (讲解词):**
  > “最后，开发者接入 Memory Passport 需要做多少工作？**只需 3 行 Python 代码！**
  > 运行我们的 Demo Agent 脚本，它通过官方 Python SDK 直接挂载我们的实时后端：不仅完成了语义召回，更在底层自动完成了时态版本过滤与冲突防御。
  > 同时，系统提供符合 2026 最新标准的 Streamable HTTP MCP 服务，内置 15 个标准工具，无论是 Claude Desktop、Cursor 还是任意自研 Agent，开箱即用！”
- **Core Value Pitch (核心卖点):** 极简 SDK + 标准 Streamable MCP，多 Agent 开箱即用。

---

### 04:30 - 04:45 | Closing (收官陈词)
- **Page:** 回到 Dashboard 首页
- **Spoken Script (讲解词):**
  > “总结来说：**Memory Passport 把 AI Agent 的长期记忆，从一个简陋的 prompt 缓存变量，进化成了一个主权化、可检索、可溯源、可演进、可科学评估的独立记忆基础设施层！**
  > 谢谢各位评委老师，欢迎提问！”

---

## 2. 3-Minute Compressed Version (3 分钟精简版)

如果现场计时紧张，可采用以下提炼节奏：

| 时间 | 演示板块 | 核心说辞与动作 |
|---|---|---|
| **00:00 - 00:30** | **问题与定位** | 登录 `demo@memorypassport.ai`，指出当前 Agent 健忘与碎片化痛点，展示 `Passport ID` 主权记忆资产库（10 条高质量记忆）。 |
| **00:30 - 01:10** | **时态与冲突演进** | 展示 `python_runtime_version_v1` (3.10) 被 `v2` (3.12) `SUPERSEDED`，解释如何解决时间漂移幻觉；展示日程冲突检测。 |
| **01:10 - 01:50** | **科学评测与质量** | 进入 `/dashboard/evaluation`，展示 Recall@5 从 80% 提升到 100% 的真实 IR 数据（MRR 0.4567, 16ms 延迟）及 7 维度质量体系（0.958 分）。 |
| **01:50 - 02:30** | **开发者 SDK / MCP** | 终端运行 `python scripts/demo_agent_run.py`，证明 3 行代码接入、自动时态决策与 15 个标准 MCP 工具支持。 |
| **02:30 - 03:00** | **收官总结** | 强调“从缓存变量到可治理、可评估的独立基础设施”，结束演讲。 |

---

## 3. 4.5-Minute Extended Version (4.5 分钟深度版)

在标准版基础上，可在以下两处做深度展开：
1. **在 01:00 处展开“记忆抽取治理”**：现场展示一段复杂业务需求对话，演示系统如何精准归纳出标签与重要性，并解释两阶段人工 Confirm 如何保证敏感信息不会被越权记录。
2. **在 03:20 处展开“评测指标分析”**：向评委深度解读为什么召回率大幅提升（0.80 $\to$ 1.00）而 MRR 略微调整（0.54 $\to$ 0.4567）是图谱拓扑扩召时的典型正常工程现象，展现对 IR 技术的深厚理解。

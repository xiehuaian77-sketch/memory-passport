# Memory Passport — Live Demo Presenter Cheat Sheet
*(路演主讲人一页纸速查备忘单 — 放在讲台/副屏备查)*

> **正式版本**：`v1.10.1-evaluation-platform`  
> **代码状态**：Commit `e68380b0447a58f7925da0ca2cc0a20a72d65496` (Clean)  
> **安全警告**：本页包含演示环境本地账密，**绝不写入公网密钥或生产 Token**。

---

## 1. 核心凭据与地址 (Credentials & Endpoints)

| 资源项 | 地址 / 凭据 | 备注 |
| :--- | :--- | :--- |
| **前端入口** | `http://localhost:3000` | Next.js 14 Dashboard |
| **后端 API 文档** | `http://127.0.0.1:8000/docs` | FastAPI Swagger UI |
| **MCP 端点** | `http://127.0.0.1:8000/mcp` | Streamable HTTP (15 Tools) |
| **演示账户邮箱** | `demo@memorypassport.ai` | 默认演示管理员 |
| **演示账户密码** | `demo123456` | 预置测试密码 |
| **演示 Passport ID** | `mp_demo_hackathon` | 核心主权护照标识 |
| **演示 Web3 钱包** | `0x71C2E63B48421882c7aE9D58E16503c403Be43F0` | SIWE 登录地址 |

---

## 2. 关键运行命令 (Command Line Arsenal)

```powershell
# 1. 一键重新灌入标准 Demo 数据 (耗时 0.5s)
python scripts/seed_demo_data.py

# 2. 验证 Demo 数据完整性 (耗时 0.8s)
pytest backend/tests/test_demo_seed.py -q

# 3. 验证 Python SDK 52项测试 (耗时 1.5s)
pytest tests/sdk -q

# 4. 后台启动后端 (端口 8000)
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 5. 启动前端生产服务 (端口 3000)
npm run start -- -p 3000
```

---

## 3. 3.5 分钟路演节奏提示卡 (Stage Cue Sheet)

| 倒计时 | 页面位置 | 核心动作 | 金句提示 |
| :--- | :--- | :--- | :--- |
| **0:00 - 0:30** | `/` -> `/login` | 演示 Web3 钱包 / 密码登录，进入控制台 | “用户换一个 Agent，记忆就归零。Memory Passport 是跨 Agent 漫游的主权记忆护照。” |
| **0:30 - 1:15** | `/memories` | 点击 `python_runtime_version_v1` -> `v2`，查看 `SUPERSEDED`；查看 `client_meeting_availability` 的 `CONFLICTED` | “传统向量库会同时搜出旧版本导致幻觉。我们通过时序引擎实现版本平滑接替与冲突拦截。” |
| **1:15 - 2:00** | `/graph` -> `/memories` (Explain) | 拖拽图谱看 5 条拓扑边；点击 Memory Explain 查看评分拆解 (Vector + FTS + Recency + Graph) | “向量是散落的点，图谱是因果网络。Memory Explain 毫秒级透视每一项数学打分，杜绝 RAG 黑盒。” |
| **2:00 - 2:50** | `/evaluations` | 页面展示 1 个 Dataset (5 cases)；并排对比 Baseline vs Enhanced 两次 Run | **背诵核心数据**：<br>• Recall 从 **0.80 -> 1.00 (100% 通过)**<br>• MRR **0.54 -> 0.4567** (图扩展拉入前置上下文)<br>• 耗时仅 **16.74ms**，质量得分 **0.958** |
| **2:50 - 3:30** | 终端 / MCP 介绍 | 展示 `POST /mcp` 与 `memory_passport` SDK (52 测试全绿) | “15 个标准 MCP 工具，无论是 Claude 还是自研 Agent，插上即可读取终身记忆。” |

---

## 4. 必须焊死在脑子里的真实数据 (Key Metrics to Memorize)

- **基准测试集**：`Developer Profile & Tech Stack Golden Dataset` (5 道测试 Case)
- **Baseline (纯关键词)**：Recall@5 = **0.8000** | MRR = **0.5400** | 平均耗时 = **2.35 ms** | 通过率 = **4/5 (80%)**
- **Enhanced (混合+图谱)**：Recall@5 = **1.0000** | MRR = **0.4567** | 平均耗时 = **16.74 ms** | 通过率 = **5/5 (100%)**
- **记忆健康度综合分**：**0.958** (覆盖 7 个维度)
- **工程质量标准**：
  - 后端自动化测试：**572 全部通过，0 失败，0 错误**
  - SDK 自动化测试：**52 全部通过**
  - Ruff 代码静态检查：**0 violations**
  - 数据库迁移：**001 至 009 全部完整**

---

## 5. 现场紧急避险与自救预案 (Emergency Runbook)

### 故障 1：页面提示“网络错误 / 无法连接后端”
- **自救**：检查 8000 端口。
  ```powershell
  Get-NetTCPConnection -LocalPort 8000
  ```
  如果进程被杀，立即在终端执行 `uvicorn app.main:app --port 8000`。

### 故障 2：前端页面展示空白或数据不一致
- **自救**：0.5 秒重新执行 Seed 恢复原始黄金快照：
  ```powershell
  python scripts/seed_demo_data.py
  ```
  然后按 `F5` 强制刷新前端浏览器。

### 故障 3：大屏幕投屏网络突然完全中断
- **自救**：
  1. 告知评委：“Memory Passport 本身就是云边端全栈支持系统，现在我们全程在纯 Localhost 离线闭环演示。”
  2. 照常演示 `http://localhost:3000`，一切数据、评测、图谱均在本地毫秒级跑通。

### 故障 4：电脑意外断电 / 极度恶劣环境
- **自救**：
  1. 备用平板打开手机热点，访问 GitHub 仓库。
  2. 投影展示 `HACKATHON_ARCHITECTURE.md` 与 `HACKATHON_DEMO_INVENTORY.md`。
  3. 播放预先存放在本地桌面上的 3 分钟高清录像切片，口播讲解。

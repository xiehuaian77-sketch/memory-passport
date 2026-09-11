# Memory Passport

一个可迁移、可控制、可追溯的 AI 记忆身份层，让用户在不同 AI 应用之间保持上下文连续。

## 技术栈

- **前端**: Next.js 14 + TailwindCSS + TypeScript
- **后端**: FastAPI + SQLAlchemy (async) + SQLite
- **AI**: OpenAI-compatible API (支持任何兼容端点)
- **认证**: JWT (邮箱注册/登录)

## 快速开始

### 1. 后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 设置你的 LLM_API_KEY 和 EMBEDDING_API_KEY

# 启动后端 (默认 http://localhost:8000)
uvicorn app.main:app --reload --port 8000
```

### 2. 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器 (默认 http://localhost:3000)
npm run dev
```

### 3. 使用

1. 打开 http://localhost:3000
2. 注册一个账号
3. 在记忆面板中添加偏好记忆
4. 在 AI 对话页测试记忆加载效果
5. 切换不同 Agent 角色验证记忆迁移

## 配置 AI 模型

项目通过环境变量支持任何 OpenAI 兼容端点：

```env
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=gpt-4o-mini

# Ollama (本地)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=llama3

# 其他兼容端点 (Azure, DeepSeek, etc.)
LLM_BASE_URL=https://your-endpoint/v1
LLM_API_KEY=your-key
LLM_MODEL=your-model
```

## API 文档

启动后端后访问: http://localhost:8000/docs

## 项目结构

```
memory-passport/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # 入口
│   │   ├── config.py         # 配置
│   │   ├── database.py       # 数据库
│   │   ├── deps.py           # 依赖注入
│   │   ├── models/           # ORM 模型
│   │   ├── schemas/          # Pydantic 模型
│   │   ├── routers/          # API 路由
│   │   └── services/         # 业务逻辑
│   └── requirements.txt
├── frontend/                 # Next.js 前端
│   ├── src/
│   │   ├── app/              # 页面 (App Router)
│   │   ├── components/       # 组件
│   │   ├── lib/              # 工具库
│   │   └── types/            # 类型定义
│   └── package.json
└── README.md
```

## License

MIT

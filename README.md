# MaxAgent

基于 LiteLLM + GitHub Copilot/GLM 的 CLI 代码助手，类似 Claude Code / OpenCode

## 功能特性

- 🤖 **智能对话**: 代码理解、问答、重构建议
- ✏️ **文件编辑**: AI 辅助代码修改，生成 unified diff
- 📋 **任务执行**: 多 Agent 协作完成复杂需求
- 🧪 **测试命令**: 测试框架检测、运行测试、AI 生成测试
- 🔧 **工具调用**: 文件操作、代码搜索、命令执行、Web 抓取
- 🧩 **SubAgent 委派**: 对话内可调用 `subagent`/`task`，包含 `shell` 子 agent 用于跑命令/装依赖并汇报，减少主上下文噪音
- 🧭 **Tool Planner (可选)**: agent 侧自动批量/并行独立只读工具调用，减少轮次与延迟（`model.enable_tool_planner=true` 或 `mcode chat --tool-planner`）
- 🧠 **Deep Thinking**: 支持 GLM/DeepSeek thinking 模型
- 📊 **Token 统计**: 实时追踪 token 用量和费用
- 🗂️ **上下文汇总**: 长对话自动滚动摘要 + 长期记忆
- 🔐 **GitHub Copilot**: 支持 OAuth 认证使用 Copilot 模型
- 🔄 **Pipe 模式**: JSONL 输出支持程序化调用

## 技术栈

- **语言**: Python 3.12+
- **CLI**: Typer + Rich
- **LLM**: 支持 GLM, OpenAI, GitHub Copilot, DeepSeek 等
- **Agent**: 原生实现 (轻量、快速)

## 安装

```bash
# 克隆项目
git clone https://github.com/maxazure/MaxAgent.git
cd MaxAgent

# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 安装依赖 (开发模式)
pip install -e .
```

## 配置

### 环境变量

```bash
# 智谱 GLM API (推荐)
export GLM_API_KEY="your-api-key"
# 或
export ZHIPU_KEY="your-api-key"

# 可选: 指定 GLM Base URL（默认 https://open.bigmodel.cn/api/coding/paas/v4）
export GLM_BASE_URL="https://open.bigmodel.cn/api/coding/paas/v4"

# OpenAI API
export OPENAI_API_KEY="your-api-key"

# GitHub Copilot (显式启用会覆盖其它 Key)
export GITHUB_COPILOT=1
```

### GitHub Copilot 认证

```bash
# 首次使用会自动提示 OAuth 认证（也可手动执行）
mcode auth copilot

# 查看认证状态
mcode auth status

# 登出
mcode auth logout copilot
```

## 快速开始

```bash
# 查看帮助
mcode -h
mcode chat -h

# 开始对话
mcode chat "解释这段代码的作用"

# 使用 thinking 模式 (适合复杂问题)
mcode chat --think "分析这个算法的复杂度"

# Pipe 模式 (JSONL 输出，用于程序化调用)
mcode chat -p "What is Python?" | jq

# 编辑文件
mcode edit src/app.py "添加错误处理"

# 执行任务 (多 Agent 协作)
mcode task "为 UserService 添加 email 查询接口"

# 测试命令
mcode test --detect           # 检测测试框架
mcode test --run              # 运行测试
mcode test --run --coverage   # 带覆盖率
mcode test --generate src/utils.py  # AI 生成测试
```

## 命令详解

### mcode chat - 智能对话

```bash
# 基本用法
mcode chat "你的问题"

# 选项
mcode chat -m gpt-4o "问题"          # 指定模型
mcode chat --think "复杂问题"        # 启用深度思考
mcode chat --no-think "简单问题"     # 禁用思考
mcode chat --no-tools "问题"         # 禁用工具调用
mcode chat -p "问题"                 # Pipe 模式 (JSONL 输出)

# REPL 模式 (交互式)
mcode chat
```

#### Pipe 模式 (-p)

Pipe 模式输出 JSONL 格式，适合程序化调用：

```bash
# 基本使用
mcode chat -p "What is Python?"

# 配合 jq 处理
mcode chat -p "Explain recursion" | jq '.content'

# 在脚本中使用
response=$(mcode chat -p "Generate a function" | jq -r '.content')
```

输出格式：
```json
{"type": "tool_call", "tool": "read_file", "success": true, "output": "..."}
{"type": "response", "content": "...", "model": "glm-4.6", "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}, "cost_usd": 0.0001}
```

#### REPL 模式命令

```
/think   - 启用深度思考
/quick   - 快速模式 (禁用思考)
/auto    - 自动思考模式
/mode    - 查看当前模式
/tokens  - 查看 token 统计
/model   - 查看当前模型
/model <name> - 切换模型
/models  - 列出可用模型
clear    - 清空历史
exit     - 退出
```

### mcode edit - 文件编辑

```bash
mcode edit <file> "修改说明"
mcode edit src/app.py "添加日志记录"
```

### mcode task - 任务执行

```bash
mcode task "需求描述"
mcode task --apply "需求描述"     # 自动应用修改
mcode task --skip-tests "需求"    # 跳过测试生成
```

### mcode test - 测试命令

```bash
mcode test detect                  # 检测测试框架
mcode test run                     # 运行测试
mcode test run -c                  # 带覆盖率
mcode test run -w                  # 监视模式
mcode test generate <file>         # AI 生成测试
```

### mcode config - 配置管理

```bash
mcode config show                  # 显示当前配置
mcode config init                  # 初始化配置文件
```

### mcode auth - 认证管理

```bash
mcode auth copilot                 # GitHub Copilot OAuth 认证
mcode auth copilot --force         # 强制重新认证
mcode auth status                  # 查看认证状态
mcode auth logout copilot          # 登出
```

## 支持的 API Provider

| Provider | 环境变量 | 默认模型 | 说明 |
|----------|----------|----------|------|
| GLM (智谱) | `GLM_API_KEY` / `ZHIPU_KEY` | glm-4.6 | 推荐 |
| OpenAI | `OPENAI_API_KEY` | gpt-4 | |
| GitHub Copilot | OAuth 认证 | gpt-4o | 首次使用会提示登录 |
| LiteLLM Proxy | `LITELLM_API_KEY` | 自定义 | |

### 使用 LiteLLM Proxy + GitHub Copilot gpt-4.1

适合想通过 LiteLLM 统一网关来用 Copilot（例如给其它客户端/Agent 共享）：

1. 安装 LiteLLM（建议版本 >= 1.40）：

```bash
pip install "litellm>=1.40"
```

2. 启动 Copilot 代理（默认端口 4000，默认模型 `gpt-4.1`）：

```bash
python scripts/start_litellm_copilot.py
```

首次请求时终端会提示 GitHub Copilot OAuth Device Flow 登录，Token 会存到 `~/.config/litellm/github_copilot/`。

3. 配置 MaxAgent 走本地代理：

```bash
unset GITHUB_COPILOT USE_COPILOT          # 避免切到直连 Copilot
export LITELLM_BASE_URL="http://localhost:4000"
export LLC_MODEL="copilot-gpt-4.1"

# 如果启动脚本里设置了 --master-key，则同时：
# export LITELLM_API_KEY="your-master-key"
```

然后正常使用 `mcode chat ...` 即可。

## Thinking 模型支持

| Provider | 模型 | 格式 |
|----------|------|------|
| GLM | glm-4.6 | `<think>` 标签 |
| DeepSeek | deepseek-reasoner, deepseek-r1 | reasoning_content |

## 可用模型列表

```
# GLM
glm-4.6

# OpenAI
gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-3.5-turbo

# DeepSeek
deepseek-chat, deepseek-reasoner

# GitHub Copilot (需要认证)
claude-3.5-sonnet, claude-3.7-sonnet, o1, o1-mini, o3-mini
```

## 项目结构

```
maxagent/
├── src/maxagent/
│   ├── cli/          # CLI 命令 (chat, edit, task, test, auth, config)
│   ├── core/         # Agent 核心 (agent, orchestrator, thinking_strategy)
│   ├── agents/       # Agent 实现 (architect, coder, tester)
│   ├── tools/        # 工具实现 (file, git, grep, glob, command, webfetch)
│   ├── llm/          # LLM 客户端 (client, copilot_client, models)
│   ├── auth/         # 认证模块 (github_copilot)
│   ├── config/       # 配置系统 (loader, schema)
│   └── utils/        # 工具函数 (console, diff, thinking, tokens)
├── docs/             # 文档
└── tests/            # 测试
```

## 工具列表

| 工具 | 说明 |
|------|------|
| read_file | 读取文件内容 |
| write_file | 写入文件 |
| list_files | 列出目录内容 |
| search_code | 搜索代码 |
| grep | 正则搜索 (支持 ripgrep) |
| glob | 文件模式匹配 |
| run_command | 执行命令 (白名单保护) |
| git_status | Git 状态 |
| git_diff | Git 差异 |
| git_log | Git 日志 |
| git_branch | Git 分支 |
| webfetch | 抓取网页内容 |

## 开发状态

当前阶段: **M5 完成** - GitHub Copilot 集成

已完成:
- ✅ M0: MVP (chat, edit, config)
- ✅ M1: 多 Agent 支持 (task)
- ✅ M2: 命令执行与 Git 工具
- ✅ M2.5: 扩展工具与指令系统 (grep, glob, webfetch)
- ✅ M3: 智能 Thinking + Test 命令
- ✅ M4: Token 统计 + 多模型切换
- ✅ M5: GitHub Copilot 集成 + Pipe 模式
- ✅ 单元测试 (105 tests, 36% coverage)

详见 [TODO.md](TODO.md)

## 测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_github_copilot.py -v

# 生成覆盖率报告
pytest tests/ --cov=src/maxagent --cov-report=html
```

## 文档

- [技术架构](docs/技术架构.md)
- [详细设计](docs/详细设计.md)
- [开发进度](TODO.md)

## License

MIT

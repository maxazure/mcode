# MaxAgent

An AI-powered CLI code assistant based on LiteLLM + GitHub Copilot/GLM, similar to Claude Code / Cursor.

[English](#features) | [中文](#功能特性)

## Features

- **Smart Chat**: Code understanding, Q&A, refactoring suggestions
- **File Editing**: AI-assisted code modifications with unified diff
- **Task Execution**: Multi-agent collaboration for complex requirements
- **Test Commands**: Test framework detection, test running, AI test generation
- **Tool Calling**: File operations, code search, command execution, web fetching
- **SubAgent Delegation**: In-conversation `subagent`/`task` calls with `shell` sub-agent
- **Deep Thinking**: Support for GLM/DeepSeek thinking models
- **Token Statistics**: Real-time tracking of token usage and costs
- **Context Summary**: Long conversation auto-summarization + long-term memory
- **GitHub Copilot**: OAuth authentication for Copilot models
- **Pipe Mode**: JSONL output for programmatic usage

## Installation

```bash
# Clone the repository
git clone https://github.com/maxazure/maxagent.git
cd maxagent

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e ".[all]"
```

## Quick Start

### 1. Configure API Provider

**Option A: GitHub Copilot (Recommended)**

```bash
# Authenticate with GitHub Copilot
mcode auth copilot

# Check authentication status
mcode auth status
```

**Option B: GLM (Zhipu AI)**

```bash
# Set environment variable
export GLM_API_KEY="your-api-key"
```

**Option C: OpenAI**

```bash
export OPENAI_API_KEY="your-api-key"
```

### 2. Start Using

```bash
# View help
mcode -h

# Start a chat
mcode chat "Explain this code"

# Use thinking mode (for complex problems)
mcode chat --think "Analyze this algorithm's complexity"

# Edit a file
mcode edit src/app.py "Add error handling"

# Execute a task (multi-agent collaboration)
mcode task "Add email query endpoint to UserService"

# List available models
mcode models list
```

## Configuration

Configuration files are stored in `~/.mcode/`:

```bash
~/.mcode/
├── config.yaml      # Main configuration
├── MAXAGENT.md      # Global instructions
└── copilot/
    └── token.json   # Copilot OAuth token
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GLM_API_KEY` / `ZHIPU_KEY` | GLM (Zhipu) API key |
| `OPENAI_API_KEY` | OpenAI API key |
| `MCODE_MODEL` | Override default model |
| `MCODE_PROVIDER` | Force specific provider |

See [.env.example](.env.example) for all options.

## Commands

### mcode chat - Smart Conversation

```bash
mcode chat "your question"
mcode chat -m gpt-4.1 "question"      # Specify model
mcode chat --think "complex question"  # Enable deep thinking
mcode chat -p "question"               # Pipe mode (JSONL output)
mcode chat                             # Interactive REPL mode
```

### mcode edit - File Editing

```bash
mcode edit <file> "modification description"
mcode edit src/app.py "Add logging"
```

### mcode task - Task Execution

```bash
mcode task "requirement description"
mcode task --apply "requirement"     # Auto-apply changes
```

### mcode test - Testing

```bash
mcode test detect                    # Detect test framework
mcode test run                       # Run tests
mcode test run -c                    # With coverage
mcode test generate <file>           # AI generate tests
```

### mcode models - Model Management

```bash
mcode models list                    # List Copilot models
mcode models list -p all             # List all configured models
mcode models list -v                 # Verbose output
```

### mcode auth - Authentication

```bash
mcode auth copilot                   # GitHub Copilot OAuth
mcode auth status                    # Check auth status
mcode auth logout copilot            # Logout
```

### mcode config - Configuration

```bash
mcode config show                    # Show current config
mcode config init                    # Initialize config file
```

## Supported Providers

| Provider | Auth Method | Default Model |
|----------|-------------|---------------|
| GitHub Copilot | OAuth | gpt-4.1 |
| GLM (Zhipu) | API Key | glm-4.6 |
| OpenAI | API Key | gpt-4 |
| LiteLLM Proxy | API Key | Custom |

## Available Tools

| Tool | Description |
|------|-------------|
| read_file | Read file content |
| write_file | Write to file |
| edit | Precise code editing |
| list_files | List directory contents |
| search_code | Search code |
| grep | Regex search (ripgrep) |
| glob | File pattern matching |
| run_command | Execute commands |
| git_status/diff/log/branch | Git operations |
| webfetch | Fetch web content |
| subagent/task | Delegate to sub-agents |
| todowrite/todoread | Task management |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/maxagent

# Code linting
ruff check src/
```

## Project Structure

```
maxagent/
├── src/maxagent/
│   ├── cli/          # CLI commands
│   ├── core/         # Agent core (agent, orchestrator)
│   ├── agents/       # Agent implementations
│   ├── tools/        # Tool implementations
│   ├── llm/          # LLM clients
│   ├── auth/         # Authentication (GitHub Copilot)
│   ├── config/       # Configuration system
│   ├── mcp/          # MCP protocol support
│   └── utils/        # Utilities
├── tests/            # Test files
└── docs/             # Documentation
```

## Contributing

See [CLAUDE.md](CLAUDE.md) for development guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## 功能特性

- **智能对话**: 代码理解、问答、重构建议
- **文件编辑**: AI 辅助代码修改，生成 unified diff
- **任务执行**: 多 Agent 协作完成复杂需求
- **测试命令**: 测试框架检测、运行测试、AI 生成测试
- **工具调用**: 文件操作、代码搜索、命令执行、Web 抓取
- **SubAgent 委派**: 对话内可调用 `subagent`/`task`
- **深度思考**: 支持 GLM/DeepSeek thinking 模型
- **Token 统计**: 实时追踪 token 用量和费用
- **上下文汇总**: 长对话自动滚动摘要 + 长期记忆
- **GitHub Copilot**: 支持 OAuth 认证使用 Copilot 模型
- **Pipe 模式**: JSONL 输出支持程序化调用

## 快速开始

```bash
# 安装
git clone https://github.com/maxazure/maxagent.git
cd maxagent
pip install -e ".[all]"

# 认证 GitHub Copilot
mcode auth copilot

# 开始使用
mcode chat "解释这段代码"
```

详细文档请参考上方英文部分。

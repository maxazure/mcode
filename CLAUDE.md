# MaxAgent 项目开发指南

## 项目概述

MaxAgent 是一个基于 LiteLLM + GitHub Copilot/GLM 的 CLI 代码助手，类似 Claude Code / OpenCode。

- **项目名称**: MaxAgent
- **CLI 命令**: `llc` / `maxagent`
- **语言**: Python 3.12+
- **包管理**: pip + hatchling
- **测试框架**: pytest + pytest-asyncio

## 项目结构

```
MaxAgent/
├── src/maxagent/
│   ├── cli/           # CLI 命令入口
│   │   ├── main.py    # 主入口, 注册所有子命令
│   │   ├── chat.py    # llc chat 命令
│   │   ├── edit.py    # llc edit 命令
│   │   ├── task.py    # llc task 命令
│   │   ├── test_cmd.py    # llc test 命令
│   │   ├── auth_cmd.py    # llc auth 命令
│   │   ├── config_cmd.py  # llc config 命令
│   │   └── mcp_cmd.py     # llc mcp 命令
│   ├── core/          # 核心 Agent 逻辑
│   │   ├── agent.py       # Agent 主类
│   │   ├── orchestrator.py    # 多 Agent 编排
│   │   ├── prompts.py     # System prompt 生成
│   │   ├── instructions.py    # 指令文件加载
│   │   └── thinking_strategy.py   # Thinking 策略
│   ├── llm/           # LLM 客户端
│   │   ├── client.py      # 通用 LLM 客户端
│   │   ├── copilot_client.py  # GitHub Copilot 客户端
│   │   ├── factory.py     # 客户端工厂 (自动选择 provider)
│   │   └── models.py      # 数据模型 (Message, ChatResponse)
│   ├── tools/         # 工具实现
│   │   ├── base.py        # Tool 基类
│   │   ├── registry.py    # 工具注册表
│   │   ├── file.py        # read_file, write_file, list_files
│   │   ├── edit.py        # edit 工具 (精确替换)
│   │   ├── search.py      # search_code
│   │   ├── grep.py        # grep 工具
│   │   ├── glob.py        # glob 工具
│   │   ├── command.py     # run_command
│   │   ├── git.py         # git_status, git_diff, git_log, git_branch
│   │   ├── webfetch.py    # webfetch 工具
│   │   ├── subagent.py    # subagent/task 委派
│   │   ├── todo.py        # todowrite, todoread, todoclear
│   │   └── memory.py      # search_memory
│   ├── config/        # 配置系统
│   │   ├── schema.py      # Pydantic 配置模型
│   │   ├── loader.py      # 配置加载器
│   │   └── agent_profiles.py  # Agent profile 加载
│   ├── auth/          # 认证模块
│   │   └── github_copilot.py  # Copilot OAuth 认证
│   ├── mcp/           # MCP 协议支持
│   │   ├── client.py      # MCP 客户端
│   │   ├── config.py      # MCP 配置
│   │   └── tools.py       # MCP 工具包装
│   └── utils/         # 工具函数
│       ├── console.py     # Rich console 输出
│       ├── context.py     # 上下文管理
│       ├── context_summary.py # 上下文摘要
│       ├── diff.py        # Diff 处理
│       ├── thinking.py    # Thinking 解析
│       └── tokens.py      # Token 计算
├── tests/             # 测试文件
├── docs/              # 文档
├── .llc.yaml          # 项目配置 (可选)
├── MAXAGENT.md        # 项目指令文件
└── pyproject.toml     # 项目配置
```

## 重要注意
每次运行测试前请确保在 .venv 环境
每次运行  llc 命令前请确保运行 pip install -e .
每次测试后请确保 安装 llc 到用户 bin 文件夹中


## 开发环境设置

```bash
# 创建虚拟环境
python3.12 -m venv .venv
source .venv/bin/activate

# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码检查
ruff check src/
mypy src/
```

## 常用命令

```bash
# 安装/更新 llc 命令
pip install -e .

# 运行 CLI
llc chat "问题"
llc chat --model gpt-4.1 "问题"   # 自动选择 GitHub Copilot
llc chat --model glm-4.6 "问题"   # 自动选择 GLM

# 运行测试
pytest tests/ -v
pytest tests/test_xxx.py -v      # 运行单个测试文件
pytest tests/ --cov=src/maxagent # 带覆盖率
```

## 配置文件

### 全局配置: `~/.llc/config.yaml`

```yaml
litellm:
  provider: "glm"  # glm, openai, github_copilot, custom

model:
  default: "glm-4.6"
  models:
    # provider/model 格式, 用于自动选择 provider
    github_copilot/gpt-4.1:
      max_tokens: 64000
    glm/glm-4.6:
      max_tokens: 128000
```

### 项目配置: `.llc.yaml`

项目根目录的配置会覆盖全局配置。

## 关键设计

### 模型自动选择 Provider

当使用 `--model` 参数时，系统会从 `config.model.models` 中查找 `provider/model` 格式的键，自动选择对应的 provider：

```python
# factory.py: get_provider_for_model()
# 1. 查找 config.model.models 中的 "provider/model" 键
# 2. 回退: 根据模型名前缀推断 (glm-* -> GLM, gpt-* -> GitHub Copilot)
```

### 工具系统

- 所有工具继承自 `BaseTool`
- 使用 `@tool` 装饰器注册
- 支持异步执行
- 工具结果自动序列化

### SubAgent 委派

- `subagent` 工具支持 `general`, `explore`, `shell` 等类型
- explore 用于代码库探索，减少主上下文 token
- shell 用于执行多步命令

## 代码规范

- 使用 ruff 进行代码检查
- 使用 mypy 进行类型检查
- 遵循 PEP 8 风格
- 所有公开函数需要类型注解和 docstring
- 测试覆盖率目标: >80%

## Git 提交规范

```bash
feat: 添加新功能
fix: 修复问题
docs: 文档更新
refactor: 代码重构
test: 测试相关
chore: 构建/工具相关
```

## 注意事项

1. **不要硬编码配置**: 模型映射等配置应从 `~/.llc/config.yaml` 动态读取
2. **避免重复读取文件**: 已读取的文件内容会缓存，避免重复调用
3. **批量操作**: 多个文件修改应尽量在一次 edit 中完成
4. **测试优先**: 修改核心逻辑前先确保有测试覆盖

## 环境变量

环境变量存储在 .env 文件中

```bash
GLM_API_KEY=
GLM_BASE_URL=https://open.bigmodel.cn/api/coding/paas/v4
```

GitHub Copilot (使用 OAuth 认证)
运行 llc auth copilot 进行认证


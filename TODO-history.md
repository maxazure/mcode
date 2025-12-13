# MaxAgent 开发历史记录

本文件记录了 MaxAgent 项目的完整开发历史，所有已完成的任务都在这里。

---

## 🔄 最新的已完成任务

### M12.5 阶段: 多 Agent 协作修复 ✅ 已完成
- [x] 修复 subagent 调用失败问题 - 完成时间: 2024-12-13 - 负责人: maxazure
  - **根本原因**: agent profiles 配置了 `model: github_copilot/gpt-4o`，但用户使用 GLM provider 且无 Copilot 认证
  - **解决方案**: 注释掉 agent profiles 中的 model 配置，使 subagent 使用主配置 provider
  - **修改文件**:
    - `~/.llc/agents/general.md` - 注释 provider 配置
    - `~/.llc/agents/web_content.md` - 注释 provider 配置
    - `~/.llc/agents/web_frontend.md` - 注释 provider 配置
    - `~/.llc/agents/web_designer.md` - 注释 provider 配置
    - `~/.llc/agents/web_pm.md` - 注释 provider 配置
    - `~/.llc/agents/web_qa.md` - 注释 provider 配置
  - **错误处理改进**: `src/maxagent/tools/subagent.py` 添加详细的 401/403/timeout 错误诊断

- [x] 改进多 Agent 测试脚本 - 完成时间: 2024-12-13 - 负责人: maxazure
  - 文件: `scripts/test_multiagent.sh`
  - **新特性**: 支持多种测试场景 (`simple`, `website`, `analyze`)
  - **日志统计**: Session 数量、工具调用统计、subagent 调用次数
  - **验证改进**: 更好的测试验证逻辑
  - **测试结果**: 3 个 Session，2 次 subagent 调用全部成功

### 配置文件目录统一 ✅ 已完成
- [x] 统一配置目录到 `~/.llc` - 完成时间: 2024-12-13 - 负责人: maxazure
  - **代码修改** (5 个文件):
    - `src/maxagent/auth/github_copilot.py`: `DEFAULT_TOKEN_DIR` → `~/.llc/copilot`
    - `src/maxagent/mcp/config.py`: `get_mcp_config_path()` → `~/.llc/mcp_servers.json`
    - `src/maxagent/config/schema.py`: `global_file` 默认值 → `~/.llc/MAXAGENT.md`
    - `src/maxagent/config/loader.py`: 配置示例路径更新
    - `src/maxagent/core/instructions.py`: 文档注释路径更新
  - **文档更新** (3 个文件):
    - `TODO.md`: 5 处路径引用更新
    - `docs/详细设计.md`: 1 处路径引用更新
    - `scripts/start_litellm_copilot.py`: 帮助文本更新
  - **配置文件迁移**:
    - `~/.config/maxagent/copilot/token.json` → `~/.llc/copilot/token.json`
    - `~/.config/maxagent/mcp_servers.json` → `~/.llc/mcp_servers.json`

---

## 📋 完整的开发历史

### M1 阶段: 基础架构 ✅ 已完成

#### Agent 框架实现
- [x] 实现 Agent 基类 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/core/agent.py`
  - 核心功能: 工具调用、消息处理、状态管理
  - 支持同步和异步模式

#### LLM 客户端实现
- [x] 实现 GLM LLM 客户端 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/llm/client.py`
  - OpenAI 兼容格式
  - 流式输出支持
  - 函数调用 (tools) 支持

#### 工具系统实现
- [x] 实现工具基类和注册表 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/tools/base.py`, `registry.py`
  - BaseTool 基类
  - ToolRegistry 工具注册表
  - 异步工具支持

- [x] 实现核心工具 - 完成时间: 2024-12-10
  - `file.py`: 文件读写操作
  - `command.py`: 命令执行
  - `git.py`: Git 操作
  - `grep.py`: 文本搜索
  - `glob.py`: 文件模式匹配
  - `search.py`: 代码搜索
  - `webfetch.py`: Web 内容获取

#### CLI 框架实现
- [x] 实现 CLI 入口和基础命令 - 完成时间: 2024-12-10
  - `main.py`: CLI 入口
  - `chat.py`: 交互式聊天命令
  - `edit.py`: 文件编辑命令
  - `task.py`: 任务执行命令
  - `config.py`: 配置管理命令

#### 配置系统实现
- [x] 实现配置加载器 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/config/loader.py`, `schema.py`
  - 多级配置支持 (全局/项目/用户)
  - 环境变量集成
  - YAML 配置格式

### M2 阶段: 增强功能 ✅ 已完成

#### 上下文管理
- [x] 实现上下文管理器 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/utils/context.py`
  - 消息历史管理
  - 上下文窗口控制
  - 自动压缩策略

#### 智能编辑功能
- [x] 实现智能 diff 和 patch - 完成时间: 2024-12-10
  - 文件: `src/maxagent/utils/diff.py`
  - 智能补丁生成
  - 冲突检测
  - 备份和恢复

#### 多 Agent 协作
- [x] 实现 Agent 编排器 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/core/orchestrator.py`
  - Agent 间通信
  - 任务分解和分配
  - 结果聚合

- [x] 实现专业化 Agent - 完成时间: 2024-12-10
  - `architect.py`: 架构师 Agent
  - `coder.py`: 编码 Agent  
  - `tester.py`: 测试 Agent

#### Agent Profiles 系统
- [x] 实现 Agent Profiles 配置 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/config/agent_profiles.py`
  - `~/.llc/agents/` 目录下的 Markdown 配置文件
  - 支持模型、工具、指令自定义

#### 指令系统
- [x] 实现指令文件加载器 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/core/instructions.py`
  - 支持 MAXAGENT.md, AGENTS.md, CLAUDE.md 等指令文件
  - Progressive discovery: 遍历父目录发现指令文件
  - 全局指令文件: ~/.llc/MAXAGENT.md

#### GitHub Copilot 集成
- [x] 实现 GitHub Copilot OAuth Device Flow 认证 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/auth/github_copilot.py`
  - OAuth Device Flow 认证流程
  - 自动打开浏览器进行授权
  - Token 持久化存储 (~/.llc/copilot/token.json)

- [x] 实现 GitHub Copilot 客户端 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/llm/copilot_client.py`
  - LiteLLM 集成
  - 自定义 HTTP 头设置
  - Editor 版本管理

- [x] 实现 Copilot CLI 命令 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/cli/auth_cmd.py`
  - `llc auth copilot`: 认证命令
  - `llc auth status`: 状态查看
  - `llc auth logout`: 登出命令

#### Thinking 系统
- [x] 实现 Thinking 基础架构 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/utils/thinking.py`
  - ThinkingStreamProcessor 支持流式处理
  - Rich Panel 显示思考过程

- [x] 更新配置系统 - 完成时间: 2024-12-10
  - 添加 InstructionsConfig 到 Config
  - 添加 thinking_model, enable_thinking, show_thinking 配置
  - 更新默认配置模板
  - 注册所有新工具到 ToolRegistry

### M3 阶段: 智能 Thinking 与指令集成 ✅ 已完成
- [x] 将指令加载器集成到 Agent - 完成时间: 2024-12-10
  - 文件: `src/maxagent/core/agent.py`
  - 在 create_agent() 中自动加载项目指令文件
  - 将指令内容合并到 system prompt
  
- [x] 实现智能 Thinking 策略选择器 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/core/thinking_strategy.py`
  - 三种策略: auto, enabled, disabled
  - auto 模式根据问题复杂度自动判断是否使用 thinking 模型
  - 支持中英文关键词检测
  - 支持多步骤任务检测

- [x] 将 deep thinking 集成到 LLM Client - 完成时间: 2024-12-10
  - 文件: `src/maxagent/llm/client.py`, `models.py`
  - 支持 GLM glm-4.6 模型 (<think> 标签格式)
  - 支持 DeepSeek deepseek-reasoner 模型 (reasoning_content 字段)
  - 自动解析和分离 thinking 内容
  - thinking_content 和 reasoning_content 字段

- [x] 更新 CLI chat 命令 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/cli/chat.py`
  - 添加 --think/--no-think 选项
  - 添加 --thinking-mode 选项 (auto/enabled/disabled)
  - REPL 模式交互命令: /think, /quick, /auto, /mode
  - 智能提示当前 thinking 模式

- [x] 更新配置系统 - 完成时间: 2024-12-10
  - thinking_strategy 替代 enable_thinking
  - 默认值: auto (根据问题复杂度自动决定)
  - 支持 GLM 和 DeepSeek thinking 模型映射

### M3 阶段续: 测试命令 ✅ 已完成
- [x] 实现 test 命令 - 完成时间: 2024-12-10
  - 文件: `src/maxagent/cli/test_cmd.py`
  - **测试框架检测**: 自动检测 pytest, unittest, jest, vitest, mocha, go test, cargo test
  - **测试执行**: 运行现有测试，支持 coverage 和 watch 模式
  - **测试生成**: 使用 AI (TesterAgent) 为指定文件生成测试
  - 子命令: detect, run, generate
  - 选项: --detect/-d, --run/-r, --generate/-g, --coverage/-c, --watch/-w, --verbose/-v

### M7 阶段: MCP (Model Context Protocol) 集成 ✅ 已完成
- [x] 实现 MCP 配置管理 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/mcp/config.py`
  - **功能**:
    - MCPServerConfig: 服务器配置 (name, url, headers, type, env_vars)
    - MCPConfig: 配置容器
    - 环境变量替换: 支持 `${VAR}` 格式
    - 持久化存储: ~/.llc/mcp_servers.json

- [x] 实现 MCP HTTP 客户端 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/mcp/client.py`
  - **功能**:
    - JSON-RPC 2.0 协议支持
    - Streamable HTTP 传输
    - SSE (Server-Sent Events) 响应处理
    - 会话管理 (Mcp-Session-Id)
    - 工具定义解析和调用

- [x] 实现 MCP Stdio 客户端 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/mcp/client.py`
  - **功能**:
    - MCPStdioClient: 子进程 stdin/stdout 通信
    - 支持本地命令执行 (如 mcp-searxng)
    - 环境变量传递和替换
    - 异步响应读取
    - create_mcp_client() 工厂函数自动选择客户端类型

- [x] 实现 MCP 工具集成 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/mcp/tools.py`
  - **功能**:
    - MCPTool: BaseTool 子类包装 MCP 工具
    - MCPToolRegistry: 全局 MCP 工具注册表
    - 自动转换为 OpenAI function schema
    - 集成到 Agent 工具系统

- [x] 实现 MCP CLI 命令 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/cli/mcp_cmd.py`
  - **子命令**:
    - `llc mcp add <name> <url>`: 添加 HTTP MCP 服务器
    - `llc mcp add <name> --command <cmd>`: 添加 Stdio MCP 服务器
    - `llc mcp remove <name>`: 移除服务器
    - `llc mcp list [-v]`: 列出已配置服务器
    - `llc mcp enable/disable <name>`: 启用/禁用服务器
    - `llc mcp test <name>`: 测试连接和列出工具
    - `llc mcp tools [name]`: 列出所有 MCP 工具
    - `llc mcp config`: 显示配置文件路径和内容

- [x] 编写 MCP 单元测试 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `tests/test_mcp.py` (43 个测试用例)
  - 测试覆盖: 配置管理、HTTP 客户端、Stdio 客户端、工具定义、错误处理

- [x] 更新文档 - 完成时间: 2024-12-10 - 负责人: maxazure
  - `docs/详细设计.md`: 添加 MCP 模块 API 文档 (section 6.6)
  - `docs/技术架构.md`: 添加 MCP 架构描述 (section 10)
  - 更新测试覆盖率统计 (148 tests, 36%)

### M8 阶段: 提示词系统重构 ✅ 已完成
- [x] 实现新的结构化提示词系统 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/core/prompts.py`
  - **功能**:
    - SystemPromptBuilder: 灵活的提示词构建器
    - 支持 Markdown + XML 混合格式
    - 动态注入环境上下文 (时间、目录、平台、Git 状态)
    - 分层结构: Identity -> Tone/Style -> Tools -> Code Quality -> Git Operations -> Context
  - **设计原则**:
    - Markdown 用于人类可读的章节标题 (# ##)
    - XML 标签用于结构化内容 (`<env>`, `<example>`)
    - 遵循 Claude Code/OpenCode/Aider 最佳实践
  - **导出函数**:
    - `build_default_system_prompt()`: 默认通用提示词
    - `build_architect_prompt()`: 架构师 Agent 提示词
    - `build_coder_prompt()`: 编码 Agent 提示词
    - `build_tester_prompt()`: 测试 Agent 提示词
    - `build_environment_context()`: 环境上下文块

- [x] 整合提示词系统到 CLI - 完成时间: 2024-12-10 - 负责人: maxazure
  - 更新 `src/maxagent/core/agent.py`: create_agent() 使用新提示词
  - 更新 `src/maxagent/agents/architect.py`: create_architect_agent() 使用新提示词
  - 更新 `src/maxagent/agents/coder.py`: create_coder_agent() 使用新提示词
  - 更新 `src/maxagent/agents/tester.py`: create_tester_agent() 使用新提示词
  - **特性**:
    - 所有 Agent 默认使用新的结构化提示词
    - 支持 `use_new_prompts=False` 回退到旧版提示词
    - 自动添加 grep/glob 工具到各 Agent
    - 自动注入项目指令文件 (MAXAGENT.md, CLAUDE.md 等)

- [x] 修复 write_file 工具路径安全问题 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/tools/file.py`
  - **问题**: 用户请求写入 `~/path` 时，工具会在项目目录下创建名为 `~` 的文件夹
  - **修复**:
    - 添加路径前缀检查：拒绝 `~` 和 `/` 开头的路径
    - 添加路径遍历检查：拒绝包含 `..` 的路径
    - 改进错误消息，明确说明只能写入项目目录内的文件
    - 更新工具描述，强调路径限制
  - **提示词更新**: 在 TOOL_USAGE_POLICY 中添加 "Path Restrictions" 章节

- [x] 添加 --yolo 模式 - 完成时间: 2024-12-11 - 负责人: maxazure
  - **功能**: 允许 AI 读写系统任意位置的文件
  - **修改文件**:
    - `src/maxagent/tools/__init__.py`: `create_registry_with_mcp()` 支持 `allow_outside_project` 参数
    - `src/maxagent/tools/file.py`: SecurityChecker, ReadFileTool, WriteFileTool 支持 YOLO 模式
    - `src/maxagent/core/orchestrator.py`: Orchestrator 支持 `allow_outside_project` 参数
    - `src/maxagent/core/prompts.py`: 添加 `TOOL_USAGE_POLICY_YOLO` 提示词，移除路径限制说明
    - `src/maxagent/core/agent.py`: `create_agent()` 支持 `yolo_mode` 参数
    - `src/maxagent/cli/chat.py`: 添加 `--yolo` 选项
    - `src/maxagent/cli/edit.py`: 添加 `--yolo` 选项
    - `src/maxagent/cli/task.py`: 添加 `--yolo` 选项
  - **使用示例**:
    ```bash
    llc chat --yolo "Read ~/some/config.json"
    llc chat --yolo --no-think "Create a snake game in ~/snake_game"
    llc edit ~/some/file.py "Add docstrings" --yolo
    llc task "Update ~/config/settings.json" --yolo
    ```
  - **警告**: 启用 YOLO 模式会显示黄色警告提示
  - **注意**: 使用 `--no-think` 避免 GLM z1 thinking 模型的 tool_calls 兼容问题

### M12 阶段: 工具增强
- [x] WebFetch 工具增强 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: `src/maxagent/tools/webfetch.py`
  - **新增功能**:
    - 使用 httpx 替代 aiohttp (已有依赖)
    - 可选 BeautifulSoup 支持 (更好的 HTML 解析)
    - 代理支持 (HTTP_PROXY/HTTPS_PROXY 环境变量)
    - 智能内容提取 (extract_main 参数)
    - 更好的 HTML 实体解码
    - 更准确的 User-Agent
    - 重定向处理改进
    - 缓存 key 包含所有参数
  - **新增参数**:
    - `extract_main`: 提取主要内容区域 (移除导航、侧边栏等)
    - `include_links`: 在文本输出中包含链接 URL
  - **可选依赖**: beautifulsoup4, lxml (通过 `pip install maxagent[web]`)

### M4 阶段: 配置化与优化
- [x] 实现 Token 统计 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: `src/maxagent/utils/tokens.py`
  - **功能**:
    - 每次调用 token 用量追踪
    - 累计费用估算 (支持 GLM, OpenAI, DeepSeek 定价)
    - REPL 模式 `/tokens` 命令查看统计
    - 响应后显示当前调用 token 用量
  - **测试**: `tests/test_tokens.py` (18 个测试用例)

- [x] 实现多模型切换 - 完成时间: 2024-12-10 - 负责人: maxazure
  - **功能**:
    - REPL 模式 `/model` 查看当前模型
    - REPL 模式 `/model <name>` 切换模型
    - REPL 模式 `/models` 列出可用模型
    - 配置系统添加 `available_models` 列表
  - **支持环境变量**: GLM_API_KEY, ZHIPU_KEY (新增)

- [x] 编写单元测试 - 完成时间: 2024-12-10 - 负责人: maxazure
  - `tests/test_thinking_strategy.py`: Thinking 策略选择器测试
  - `tests/test_test_cmd.py`: 测试命令和框架检测测试
  - `tests/test_config_loader.py`: 配置加载器测试
  - `tests/test_tools_base.py`: 工具基类测试
  - `tests/test_tokens.py`: Token 统计功能测试
  - `tests/test_mcp.py`: MCP 模块测试 (56 个测试用例，含连接状态测试)
  - `tests/test_context.py`: 上下文管理测试 (25 个测试用例)
  - 测试覆盖率: 36% (186 测试用例)

- [x] 端到端集成测试 (Snake Game) - 完成时间: 2024-12-10 - 负责人: maxazure
  - 测试目录: `tests/e2e/snake_game_test/`
  - **测试场景**: 使用 llc 生成 Snake 游戏
  - **测试结果**:
    - `llc task` 架构分析: 通过 - 正确生成实现计划
    - `llc chat` 工具调用: 通过 - read_file 工具正常工作
    - `llc chat --think` 深度思考: 部分通过 - 思考过程正常，输出格式需优化
    - Snake 游戏代码: 通过 - 语法正确，可正常导入

- [x] 端到端集成测试 (FastAPI) - 完成时间: 2024-12-10 - 负责人: maxazure
  - 测试目录: `tests/e2e/fastapi_test/`
  - **测试场景**: 多文件 FastAPI Todo API 项目
  - **项目结构**:
    - `app/main.py`: FastAPI 应用入口
    - `app/models.py`: Pydantic 模型 (Todo, TodoCreate, TodoUpdate)
    - `app/database.py`: 内存数据库模拟
    - `app/routes/todos.py`: CRUD 端点
    - `requirements.txt`: 依赖列表
  - **测试结果**:
    - `llc chat` 项目分析: 通过 - 正确读取和分析多个文件
    - FastAPI 应用导入: 通过
    - API 端点测试: 全部通过 (GET/POST/PUT/DELETE)
    - 404 错误处理: 通过

- [x] 修复已发现的问题 - 完成时间: 2024-12-10 - 负责人: maxazure
  - `llc edit` 命令: 修复 Typer 参数解析问题

---

## 💡 优化建议 (已完成)

- [x] 支持多模型配置和切换 - 完成时间: 2024-12-10 - 预期收益: 灵活性
- [x] 支持 MCP (Model Context Protocol) - 完成时间: 2024-12-10 - 预期收益: 扩展性

---

## 📚 技术要点总结

### 上下文管理与 Token 追踪

#### 为什么需要上下文管理
- LLM 有固定的上下文窗口限制 (如 GLM-4: 128K, GPT-4: 8K)
- 长对话会逐渐填满上下文，导致 API 调用失败或超时
- 工具调用返回大量内容时，上下文增长非常快

#### Token 估算策略
```python
# 中文: ~1.5 字符/token
# 英文: ~4 字符/token
chinese_tokens = chinese_chars / 1.5
english_tokens = other_chars / 4
```

#### 上下文压缩策略
1. **保留 system prompt**: 始终保留，因为包含重要指令
2. **保留最近消息**: 至少保留最近 N 条消息 (默认 4 条)
3. **FIFO 删除**: 删除最旧的消息直到满足目标大小
4. **阈值触发**: 当使用率超过 80% 时开始压缩

#### 使用方式
```bash
# 启用上下文调试
llc chat --debug-context "Your message"

# REPL 模式查看上下文
/context

# 输出示例
Context Debug [glm-4.6]
├─ Total: 1,369/128,000 tokens (1.1%)
├─ Messages: 2
├─ System: 1,354 tokens
├─ User: 15 tokens
├─ Assistant: 0 tokens
├─ Tool: 0 tokens
└─ Remaining: 126,631 tokens
```

#### 模型上下文限制
| 模型 | 上下文限制 |
|------|-----------|
| glm-4.6 | 128,000 |
| gpt-4 | 8,192 |
| gpt-4-turbo | 128,000 |
| gpt-4o | 128,000 |
| deepseek-chat | 64,000 |
| claude-3.5-sonnet | 200,000 |

### 智谱 GLM API 集成要点
- 端点: `GLM_BASE_URL` (默认为 https://open.bigmodel.cn/api/coding/paas/v4) — 可通过 .env 配置
- 使用标准 OpenAI 兼容格式
- 支持流式输出和函数调用 (tools)
- 模型列表: glm-4.6, glm-4.6, glm-4.6v 等
- Thinking 模型: glm-4.6
- 环境变量: `GLM_API_KEY` 或 `ZHIPU_KEY`

### Thinking/Reasoning 模型集成要点

#### 支持的 Thinking 模型
| Provider | 模型 | 格式 | 特点 |
|----------|------|------|------|
| GLM | glm-4.6 | `<think>...
</think>

` 标签 | 内嵌在 content 中 |
| DeepSeek | deepseek-reasoner | `reasoning_content` 字段 | 独立字段 |
| DeepSeek | deepseek-r1 | `reasoning_content` 字段 | 独立字段 |

#### Thinking 策略
- **disabled**: 从不使用 thinking 模型
- **enabled**: 始终使用 thinking 模型
- **auto** (默认): 根据问题复杂度自动判断

#### Auto 模式判断规则
1. 复杂问题关键词: 分析、推理、设计、调试、优化等
2. 代码任务关键词: bug、fix、implement、重构等
3. 消息长度 > 150 字符
4. 包含代码块 (```)
5. 多步骤任务 (1. 2. 3. 或 first/then/finally)
6. 多个问题 (>=2 个问号)

#### CLI 使用方式
```bash
# 强制启用 thinking
llc chat --think "Analyze this algorithm"

# 强制禁用 thinking
llc chat --no-think "What is Python?"

# 指定模式
llc chat --thinking-mode=auto "Design a solution"

# REPL 模式命令
/think   # 启用 thinking
/quick   # 禁用 thinking
/auto    # 自动模式
/mode    # 查看当前模式
```

### LiteLLM + GitHub Copilot 集成要点
- 使用 `github_copilot/` 前缀调用模型
- 首次使用需要 OAuth Device Flow 认证
- 需要设置 `editor-version` 和 `Copilot-Integration-Id` headers
- Token 存储在 `~/.config/litellm/github_copilot/`

### Agent 框架选型结论
- **原生实现**最适合 CLI 工具场景
- 冷启动时间要求 <500ms，重框架无法满足
- 参考 LangGraph 状态管理思想
- 参考 CrewAI 角色分工模式

### CLI 框架选型结论
- **Typer** 提供最佳开发体验
- 类型提示直接定义参数
- Rich 集成提供漂亮的终端 UI
- 底层基于 Click，可回退使用高级功能

### 项目结构
```
src/maxagent/
├── __init__.py
├── __main__.py
├── auth/                     # 认证模块 (新增)
│   ├── __init__.py
│   └── github_copilot.py     # GitHub Copilot OAuth 认证
├── cli/
│   ├── auth_cmd.py           # auth 命令 (新增)
│   ├── chat.py               # chat 命令 (含 thinking 支持)
│   ├── config_cmd.py         # config 命令
│   ├── edit.py               # edit 命令
│   ├── main.py               # CLI 入口
│   ├── mcp_cmd.py            # mcp 命令 (新增)
│   ├── task.py               # task 命令
│   └── test_cmd.py           # test 命令
├── config/
│   ├── loader.py             # 配置加载 (支持多 API Provider)
│   └── schema.py             # 配置模型 (含 InstructionsConfig, thinking_strategy)
├── core/
│   ├── agent.py              # Agent 基类 (自动加载指令)
│   ├── instructions.py       # 指令文件加载器
│   ├── orchestrator.py       # Agent 编排器
│   └── thinking_strategy.py  # Thinking 策略选择器
├── agents/
│   ├── architect.py          # 架构师 Agent
│   ├── coder.py              # 编码 Agent
│   └── tester.py             # 测试 Agent
├── llm/
│   ├── client.py             # LLM 客户端 (含 thinking 处理)
│   ├── copilot_client.py     # GitHub Copilot 客户端 (新增)
│   └── models.py             # 数据模型 (含 thinking_content)
├── mcp/                      # MCP 模块 (新增)
│   ├── __init__.py
│   ├── client.py             # MCP HTTP 客户端 (Streamable HTTP)
│   ├── config.py             # MCP 配置管理
│   └── tools.py              # MCP 工具集成
├── tools/
│   ├── base.py               # Tool 基类
│   ├── command.py            # 命令执行
│   ├── file.py               # 文件操作
│   ├── git.py                # Git 工具
│   ├── glob.py               # Glob 模式匹配
│   ├── grep.py               # Grep 搜索
│   ├── registry.py           # Tool 注册表
│   ├── search.py             # 代码搜索
│   └── webfetch.py           # Web 内容获取
└── utils/
    ├── console.py            # 控制台工具
    ├── diff.py               # Diff 处理
    ├── thinking.py           # Deep thinking 处理
    └── tokens.py             # Token 统计
```

### 支持的 API Provider

| Provider | 环境变量 | 默认 Base URL | 默认模型 |
|----------|----------|---------------|----------|
| GLM (智谱) | `GLM_API_KEY` | `GLM_BASE_URL` (默认为 https://open.bigmodel.cn/api/coding/paas/v4) | `glm-4.6` |
| OpenAI | `OPENAI_API_KEY` | `https://api.openai.com/v1` | `gpt-4` |
| GitHub Copilot | OAuth 认证 | `https://api.githubcopilot.com` | `gpt-4o` |
| LiteLLM | `LITELLM_API_KEY` | `http://localhost:4000` | 自定义 |
| Custom | 手动配置 | 自定义 | 自定义 |

### GitHub Copilot 集成

#### 认证流程
```bash
# 首次使用前需要认证
llc auth copilot

# 认证流程:
# 1. 自动打开浏览器 https://github.com/login/device
# 2. 输入显示的用户码 (如 ABCD-1234)
# 3. 在 GitHub 上授权
# 4. Token 自动保存到 ~/.llc/copilot/token.json
```

#### 使用方式
```bash
# 设置环境变量启用 Copilot
export GITHUB_COPILOT=1
llc chat "Hello!"

# 或在 REPL 中切换模型
llc chat
/model gpt-4o
/model claude-3.5-sonnet
```

#### 可用模型
- gpt-4o, gpt-4o-mini
- claude-3.5-sonnet, claude-3.7-sonnet
- o1, o1-mini, o3-mini

#### X-Initiator 计费优化
GitHub Copilot 使用 `X-Initiator` header 追踪 premium requests:
- 每个会话的第一条消息: `X-Initiator: user` (计费)
- 后续消息 (工具调用等): `X-Initiator: agent` (不计费)

这避免了多轮对话重复计费的问题。

#### 管理命令
```bash
llc auth status          # 查看认证状态
llc auth logout copilot  # 登出 (删除本地 token)
llc auth copilot --force # 强制重新认证
```

### 快速开始

```bash
# 使用智谱 GLM API
export GLM_API_KEY="your-api-key"
llc chat "Hello, introduce yourself"

# 使用 OpenAI API
export OPENAI_API_KEY="your-api-key"
llc chat "Hello, introduce yourself"

# 查看项目文件
llc chat "What files are in the src directory?"

# 编辑文件
llc edit src/app.py "Add a health check endpoint"

# 执行复杂任务
llc task "Implement user authentication feature"

# 测试命令
llc test --detect              # 检测测试框架
llc test --run                 # 运行所有测试
llc test --run --coverage      # 运行测试并生成覆盖率报告
llc test --run --watch         # 监视模式运行测试
llc test --generate src/utils.py  # 使用 AI 为文件生成测试

# Pipe Mode (JSONL 输出，适合脚本集成)
llc chat -p "What is Python?" | jq
llc edit -p src/app.py "Add logging" | jq
llc task -p "Add error handling" | jq
```

### Pipe Mode 详解

#### 输出格式
Pipe mode 输出 JSONL (JSON Lines) 格式，每个事件一行 JSON：

```bash
# Chat 命令输出
{"type": "tool_call", "tool": "read_file", "success": true, "output": "..."}
{"type": "response", "content": "Hello!", "model": "glm-4.6", "usage": {...}, "cost_usd": 0.0001}

# Edit 命令输出
{"type": "tool_call", "tool": "read_file", "success": true, "output": "..."}
{"type": "edit_response", "file": "src/app.py", "patches": [...], "model": "glm-4.6", ...}

# Task 命令输出
{"type": "progress", "agent": "architect", "status": "Analyzing requirements..."}
{"type": "task_result", "summary": "...", "patches": [...], "tests": [...]}
```

#### 使用场景
```bash
# 提取响应内容
llc chat -p "Explain Python" | jq -r '.content'

# 提取 patches
llc edit -p src/app.py "Add logging" | jq -r '.patches[].content'

# 获取 token 使用量
llc chat -p "Hello" | jq '.usage'

# 批处理脚本集成
for file in *.py; do
  llc edit -p "$file" "Add docstrings" | jq -r '.patches[].content' > "${file}.patch"
done
```

### Test 命令详解

#### 支持的测试框架
| 框架 | 语言 | 检测方式 | 运行命令 |
|------|------|----------|----------|
| pytest | Python | pytest.ini, pyproject.toml, setup.cfg | `pytest` |
| unittest | Python | `import unittest` in test files | `python -m unittest discover` |
| Jest | JavaScript/TypeScript | package.json | `npm test` / `npx jest` |
| Vitest | JavaScript/TypeScript | package.json | `npx vitest run` |
| Mocha | JavaScript/TypeScript | package.json | `npm test` / `npx mocha` |
| Go test | Go | go.mod + *_test.go files | `go test ./...` |
| Cargo test | Rust | Cargo.toml | `cargo test` |

#### 命令使用
```bash
# 检测项目使用的测试框架
llc test detect
llc test --detect
llc test -d

# 运行测试
llc test run                   # 运行所有测试
llc test run tests/test_utils.py  # 运行特定测试文件
llc test run -v                # 详细输出
llc test run -c                # 带覆盖率
llc test run -w                # 监视模式

# 生成测试 (使用 AI)
llc test generate src/module.py    # 为指定文件生成测试
llc test --generate src/module.py  # 同上
```

### Token 统计功能

#### 功能特点
- **实时统计**: 每次 API 调用后显示 token 用量和费用
- **累计统计**: 在 REPL 模式中累计整个会话的 token 使用
- **多模型支持**: 支持 GLM, OpenAI, DeepSeek 等模型的定价计算
- **详细报表**: 使用 `/tokens` 命令查看详细的使用统计表

#### REPL 模式命令
```bash
# 进入 REPL 模式
llc chat

# 查看 token 统计
/tokens           # 显示详细统计表

# 模型切换
/model            # 查看当前模型
/model glm-4.6    # 切换到 glm-4.6
/models           # 列出可用模型
```

#### 输出示例
```
╭───────────────────────────────── Assistant ──────────────────────────────────╭
│ Hello! How can I help you today?                                             │
╰──────────────────────────────────────────────────────────────────────────────╯
Tokens: 1,825 (↑1,703 ↓122) | $0.0009
```

#### Token 统计表示例
```
              Token Usage Statistics
┏━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ Model        ┃ Requests ┃   Input ┃  Output ┃   Total ┃  Cost (USD) ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━┩
│ glm-4.6      │        3 │   5,092 │     558 │   5,650 │     $0.0028 │
├──────────────┼──────────┼─────────┼─────────┼─────────┼─────────────┤
│ Total        │        3 │   5,092 │     558 │   5,650 │     $0.0028 │
└──────────────┴──────────┴─────────┴─────────┴─────────┴─────────────┘
```

### MCP (Model Context Protocol) 集成

#### 概述
MCP 是 Anthropic 推出的模型上下文协议，允许 AI 模型访问外部工具和数据源。
MaxAgent 支持通过 HTTP 和 Stdio 两种传输方式连接 MCP 服务器，扩展 AI 的能力。

#### 支持的传输类型
| 类型 | 说明 | 适用场景 |
|------|------|----------|
| HTTP | Streamable HTTP (JSON-RPC 2.0) | 远程 MCP 服务器 (如智谱 web_reader) |
| Stdio | 子进程 stdin/stdout 通信 | 本地 MCP 服务器 (如 mcp-searxng) |

#### 配置存储
- 配置文件: `~/.llc/mcp_servers.json`
- 支持环境变量替换: `${VAR}` 格式

#### CLI 命令
```bash
# 添加 HTTP MCP 服务器
llc mcp add web-reader https://api.example.com/mcp --header "Authorization: Bearer ${API_KEY}"

# 添加 Stdio MCP 服务器 (本地命令)
llc mcp add searxng --command mcp-searxng --env "SEARXNG_URL=http://localhost:8888"

# 添加带参数的 Stdio 服务器
llc mcp add myserver --command python --arg "-m" --arg "my_mcp_server"

# 列出已配置的服务器
llc mcp list
llc mcp list -v  # 详细信息

# 测试服务器连接
llc mcp test web-reader

# 列出所有 MCP 工具
llc mcp tools
llc mcp tools web-reader  # 指定服务器

# 启用/禁用服务器
llc mcp enable web-reader
llc mcp disable web-reader

# 移除服务器
llc mcp remove web-reader

# 查看配置文件
llc mcp config
```

#### 智谱 GLM web_reader 集成示例 (HTTP)
```bash
# 添加智谱 web_reader MCP 服务器
llc mcp add web-reader https://open.bigmodel.cn/api/mcp/web_reader/mcp \
    --header "Authorization: Bearer ${ZHIPU_KEY}"

# 测试连接
llc mcp test web-reader

# 在 chat 中使用
llc chat "Use web-reader to fetch https://example.com and summarize it"
```

#### Searxng MCP 服务器示例 (Stdio)
```bash
# 安装 mcp-searxng
pip install mcp-searxng

# 添加 Stdio MCP 服务器
llc mcp add searxng --command mcp-searxng --env "SEARXNG_URL=http://192.168.31.205:8888"

# 测试连接
llc mcp test searxng

# 在 chat 中使用
llc chat "Search for Python tutorials using searxng"
```

#### 技术实现
- **HTTP 传输**: Streamable HTTP (JSON-RPC 2.0) + SSE 响应
- **Stdio 传输**: 子进程 stdin/stdout + JSON-RPC 2.0
- **会话管理**: 支持 Mcp-Session-Id (HTTP)
- **协议版本**: 2025-06-18 / 2024-11-05
- **工厂函数**: `create_mcp_client()` 根据配置自动选择客户端类型

#### 工具集成
MCP 工具自动注册到 Agent 的工具系统中:
- 工具名格式: `mcp_{server_name}_{tool_name}`
- 描述前缀: `[MCP:{server_name}]`
- 自动转换为 OpenAI function schema

---

**此文件记录了 MaxAgent 项目的完整开发历程。所有已完成的功能、优化和修复都在这里。**
# MaxAgent TODO 任务列表

## 🔄 进行中

*无*

## ✅ 已完成

### M12.3 阶段: 并行编辑多文件优化 ✅ 已完成
- [x] 优化多文件编辑的请求效率 - 完成时间: 2024-12-13 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **问题**: LLM 在修改多个文件时，会逐个更新 todo 状态 (in_progress → edit → completed)，导致 7+ 个请求处理 3 个文件
  - **解决方案**:
    - 在 PLAN_EXECUTE_WORKFLOW 中添加 "ABSOLUTE RULE" 强调不要单独调用 todowrite 更新状态
    - 明确禁止 "in_progress" 状态更新，直接从 "pending" 到 "completed"
    - 添加 ❌ FORBIDDEN PATTERNS 和 ✅ CORRECT PATTERN 示例
    - 更新 Phase 2 和 Phase 3 说明，强调跳过 "in_progress"
    - 更新 PLAN_EXECUTE_HEADLESS 添加 "THE GOLDEN RULE: BATCH EVERYTHING"
    - 添加具体的代码示例展示正确的批量执行模式
  - **测试验证**:
    - 简单多文件任务 (添加注释头): ✅ 3 个请求处理 3 个文件 (read all → edit all → done)
    - 复杂多文件任务: 仍可能需要额外请求进行分析，但核心编辑阶段已优化

### M12.2 阶段: 批量编辑优化 ✅ 已完成
- [x] 强化批量编辑提示词 - 完成时间: 2024-12-13 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **改进**:
    - 在 TOOL_USAGE_POLICY 开头添加 "🚨🚨🚨 CRITICAL: ONE EDIT CALL PER FILE" 章节
    - 强调 "You may only call edit ONCE per file in your ENTIRE response"
    - 添加 ABSOLUTELY FORBIDDEN 清单和详细 CORRECT/WRONG 示例
    - 重构 EFFICIENCY RULES 强调 PHASE 1-Read → PHASE 2-Plan → PHASE 3-Execute 工作流
    - 简化 File Operations 决策树和 Edit Tool Usage 说明
    - 同步更新 TOOL_USAGE_POLICY_YOLO 提示词

- [x] 优化编辑警告系统 - 完成时间: 2024-12-13 - 负责人: maxazure
  - 文件: src/maxagent/core/agent.py
  - **改进**:
    - 将 `_excessive_edit_threshold` 从 3 改为 2
    - 强化警告消息，使用 🚨🚨🚨 CRITICAL VIOLATION 格式
    - 在警告中包含正确的代码示例，指导 LLM 使用 `edits` 数组
  - **测试验证**:
    - 单文件多改动: ✅ 使用 `edits: [5 items]` 一次调用完成
    - 多文件各一个改动: ✅ 每个文件只调用一次 edit
    - 配置优化任务: ✅ 正确使用批量编辑

### M12.1 阶段: 模型特定配置支持 ✅ 已完成
- [x] 实现模型特定配置功能 - 完成时间: 2024-12-12 - 负责人: maxazure
  - **功能**: 允许为每个模型单独配置 max_tokens、context_length 和 temperature
  - **修改文件**:
    - src/maxagent/config/schema.py: 添加 ModelSpecificConfig 类和 models 字段
    - src/maxagent/utils/context.py: 更新 get_model_context_limit() 支持配置优先级
    - src/maxagent/llm/factory.py: 添加 get_model_max_tokens() 和 get_model_temperature()
  - **配置格式**:
    ```yaml
    model:
      default: gpt-4o
      max_tokens: 4096           # 全局默认
      context_length: 128000     # 全局默认
      models:                    # 模型特定配置
        gpt-4o:
          max_tokens: 8192
          context_length: 128000
        deepseek-chat:
          max_tokens: 4096
          context_length: 64000
          temperature: 0.5
    ```
  - **配置优先级**: 模型特定配置 > 硬编码默认值 > 全局配置
  - **测试**: tests/test_model_specific_config.py (19 个测试用例)

- [x] 实现 Provider 特定配置支持 - 完成时间: 2024-12-12 - 负责人: maxazure
  - **功能**: 同一模型在不同供应商下可能有不同的限制，支持按 provider/model 格式配置
  - **修改文件**:
    - src/maxagent/utils/context.py: get_model_context_limit() 添加 provider 参数
    - src/maxagent/llm/factory.py: get_model_max_tokens/temperature() 添加 provider 参数
    - src/maxagent/utils/context.py: ContextManager/AsyncContextManager 添加 provider 属性
  - **配置格式**:
    ```yaml
    model:
      default: gpt-4o
      max_tokens: 4096
      context_length: 128000
      models:
        # Provider 特定配置 (优先级最高)
        github_copilot/gpt-4o:
          max_tokens: 4096
          context_length: 100000
        openai/gpt-4o:
          max_tokens: 16384
          context_length: 128000
        # 模型默认配置 (无 provider 时使用)
        gpt-4o:
          max_tokens: 8192
          context_length: 128000
    ```
  - **配置优先级**: Provider特定配置 > 模型特定配置 > 硬编码默认值 > 全局配置
  - **测试**: tests/test_model_specific_config.py (24 个测试用例)

### M11.7 阶段: Write 工具保留原有代码问题 ✅ 已完成
- [x] 调查 LLM 使用 write_file 覆盖原有代码问题 - 完成时间: 2024-12-11 - 负责人: maxazure
  - **问题现象**: `llc chat "给 calculator.py 添加功能，让它变成科学计算器"`
    - LLM 读取文件后没有输出任何内容（Assistant 面板为空）
    - 或者 LLM 使用 write_file 但没有保留原有函数
  - **根本原因**: 
    1. 原始问题是 LLM 偶尔不完成任务（可能是 API 响应问题）
    2. 提示词中 "Mentally combine" 表述模糊，未强调必须保留原有代码

- [x] 优化 TOOL_USAGE_POLICY 中 write_file 指导 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **改进**:
    - 将 "Mentally combine" 改为 "CRITICAL: PRESERVE all existing code"
    - 添加详细示例展示如何保留原有函数并添加新函数
    - 强调 "Write the COMPLETE file with both old and new code"
  - **同步更新**: TOOL_USAGE_POLICY_YOLO 提示词
  - **测试验证**: `llc chat "给 calculator.py 添加 sin, cos, tan, log, exp 函数"` 现在正确保留原有代码

### M11.6 阶段: Edit vs Write 工具使用指导优化 ✅ 已完成
- [x] 分析 LLM 使用 edit 工具时代码缩进错误的问题 - 完成时间: 2024-12-11 - 负责人: maxazure
  - **问题现象**: `llc chat "给 calculator.py 添加功能，让它变成完备计算器"`
    - LLM 使用 edit 工具在 `return a * b` 后插入新函数
    - 但 `new_string` 包含错误缩进（4空格），导致新函数被嵌套在 multiply 内部
  - **根本原因**: 提示词过度强调 "PREFER edit tool"，导致 LLM 在不适合的场景也使用 edit
  - **结论**: 这是 LLM 理解问题，不是 edit 工具的 bug

- [x] 优化 TOOL_USAGE_POLICY 提示词 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **改进**:
    - 添加 "Choose the right tool based on scope" 决策表
    - 明确 edit 适用场景: 小修改、添加 docstring、rename、修 bug
    - 明确 write_file 适用场景: 添加多个新函数、大规模重构、创建新文件
    - 添加关键规则: "Avoid nested insertions"
    - 更新示例代码
  - **同步更新**: TOOL_USAGE_POLICY_YOLO 提示词

- [x] 修复 tests/e2e/calculator.py 测试文件 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 重写为正确的完备计算器实现（add, subtract, multiply, divide）

### M11.5 阶段: 单次 Chat 模式工具执行修复 ✅ 已完成
- [x] 修复单次 chat 模式不执行工具问题 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/cli/chat.py
  - **问题**: 用户运行 `llc chat "..."` 时，LLM 只输出执行计划而不实际调用工具
  - **根本原因**: 单次 chat 模式使用了 `interactive_mode=True`，导致使用了 `PLAN_EXECUTE_INTERACTIVE` 提示词
  - **修复**:
    - 将单次 chat 模式改为 `interactive_mode=False` (第 216 行)
    - 使用 `PLAN_EXECUTE_HEADLESS` 提示词，强调直接执行工具
  - **测试验证**: `llc chat "给 tests/e2e/calculator.py 的 multiply 函数添加类型注解"` 现在正确执行

- [x] 优化 PLAN_EXECUTE_HEADLESS 提示词 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **改进**:
    - 强调 "ACTUALLY DO IT using tool calls"
    - 添加 WRONG/CORRECT 示例区分输出 JSON vs 实际调用
    - 区分简单任务（直接执行）和复杂任务（需要计划）

- [x] 清理 PLAN_EXECUTE_WORKFLOW 残留代码 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 删除了旧模板的示例代码残留（843-878 行）

### M11.4 阶段: Edit 工具文档更新 ✅ 已完成
- [x] 更新 docs/详细设计.md - 完成时间: 2024-12-11 - 负责人: maxazure
  - 添加 Edit 工具项目结构条目
  - 新增 6.7 章节: Edit 工具 API 文档
  - 包含: 核心类、Replacer 策略、使用示例、CLI 使用、安全机制
  - 更新测试覆盖统计 (274 测试用例)

- [x] 更新 docs/技术架构.md - 完成时间: 2024-12-11 - 负责人: maxazure
  - 更新 Tool 系统表格，添加 Edit 工具条目
  - 更新测试覆盖统计
  - 新增 11 章节: Edit 工具架构设计
  - 包含: 设计背景、架构图、Replacer 策略链、Levenshtein 距离、工具流程

### M11.3 阶段: Edit 工具实现 (Search-Replace) ✅ 已完成
- [x] 研究 Claude Code/OpenCode Edit 工具实现 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 研究来源: OpenCode (sst/opencode) 的 edit.ts
  - **核心设计**: Search-and-Replace (str_replace) 方式
  - **参数**: file_path, old_string, new_string, replace_all
  - **安全机制**: 必须先读取文件、精确匹配、唯一性检查

- [x] 创建新的 EditTool - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/edit.py
  - **核心功能**:
    - `edit` 工具用于精确修改现有文件
    - 使用 search-and-replace 而非覆盖整个文件
    - 支持 `replace_all` 批量替换

- [x] 实现多种 Replacer 策略 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/edit.py
  - **策略列表** (按优先级):
    1. `simple_replacer` - 精确字符串匹配
    2. `line_trimmed_replacer` - 行首尾空白修剪匹配
    3. `block_anchor_replacer` - 块锚点匹配 (首尾行 + 相似度)
    4. `whitespace_normalized_replacer` - 空白标准化匹配
    5. `indentation_flexible_replacer` - 缩进灵活匹配
    6. `escape_normalized_replacer` - 转义字符标准化
    7. `trimmed_boundary_replacer` - 边界修剪匹配
    8. `context_aware_replacer` - 上下文感知匹配
    9. `multi_occurrence_replacer` - 多次出现匹配
  - **Levenshtein 距离**: 用于相似度计算

- [x] 更新工具注册表 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/__init__.py
  - 添加 EditTool 到 `__all__` 导出
  - 在 `create_default_registry()` 中注册 EditTool

- [x] 更新配置默认启用工具 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/config/schema.py
  - 将 `edit` 添加到 ToolsConfig.enabled 默认列表

- [x] 更新提示词系统 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **TOOL_USAGE_POLICY 更新**:
    - 添加 "Editing Files - IMPORTANT" 章节
    - 强调优先使用 `edit` 工具修改现有文件
    - 仅在创建新文件时使用 `write_file`
    - 添加 Edit 工具使用示例

- [x] 添加单元测试 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: tests/test_edit.py (41 个测试用例)
  - **测试覆盖**:
    - Levenshtein 距离算法
    - 各种 Replacer 策略
    - replace_content 核心函数
    - create_unified_diff 函数
    - EditTool 类完整功能
    - 集成测试（添加 docstring、重命名变量、修改函数等）

### M11.1 阶段: Todo 工具 E2E 测试与修复 ✅ 已完成
- [x] Todo 功能 E2E 测试 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: tests/test_todo.py (47 个测试用例)
  - **测试覆盖**:
    - TodoItem 数据类测试
    - TodoList 完整 CRUD 操作测试
    - TodoWriteTool 工具测试
    - TodoReadTool 工具测试
    - TodoClearTool 工具测试
    - 全局函数测试
    - 集成测试（完整工作流、并发操作）
    - 边界情况测试（特殊字符、Unicode、长内容、空内容、重复ID等）
    - Schema 测试

- [x] 修复 ToolParameter 不支持数组 items 定义 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/base.py
  - **问题**: ToolParameter 类不支持定义数组元素的结构
  - **影响**: LLM 不知道 todowrite 工具的 todos 数组应该包含什么结构
  - **修复**:
    - 添加 `items: Optional[dict[str, Any]]` 字段支持数组元素定义
    - 添加 `properties: Optional[dict[str, Any]]` 字段支持对象属性定义
    - 更新 `to_openai_schema()` 方法生成完整的 JSON Schema

- [x] 修复 Todo 工具未在默认启用列表中 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/config/schema.py
  - **问题**: ToolsConfig.enabled 默认列表未包含 todo 工具
  - **影响**: 即使工具已注册，LLM 也看不到它们的 schema
  - **修复**: 将 `todowrite`, `todoread`, `todoclear` 添加到默认启用工具列表

- [x] 更新 TodoWriteTool 参数定义 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/todo.py
  - **改进**: 为 todos 参数添加完整的 items schema 定义
  - **效果**: LLM 现在可以正确理解 todos 数组的结构

### M11.2 阶段: Plan-Execute 工作流 ✅ 已完成
- [x] 实现 Plan-Execute 工作流 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
  - **功能**:
    - `PLAN_EXECUTE_WORKFLOW`: 核心工作流提示词，要求 LLM 在修改前先制定计划
    - `PLAN_EXECUTE_INTERACTIVE`: 交互模式提示词，要求用户确认后再执行
    - `PLAN_EXECUTE_HEADLESS`: 无头模式提示词，自动执行计划
  - **工作流程**:
    1. Planning Phase: 理解需求 → 研究分析 → 制定执行计划 → 创建 Todo List
    2. Execution Phase: 逐个执行任务，更新状态
    3. Verification Phase: 验证结果，汇报完成情况

- [x] 增强 Todo 工具支持技术细节 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/todo.py
  - **新增字段**:
    - `file_path`: 任务相关的目标文件路径
    - `details`: 技术实现细节
  - **效果**: Todo 不再只是简单任务列表，而是包含技术细节的执行计划

- [x] 实现双模式支持 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/agent.py, src/maxagent/cli/chat.py
  - **交互模式 (Chat)**: `interactive_mode=True`
    - 制定计划后等待用户确认
    - 用户可以审查、修改或取消计划
  - **无头模式 (Pipe)**: `interactive_mode=False`
    - 制定计划后自动执行
    - 适合程序化调用和自动化场景

### M11 阶段: 高级工具增强 ✅ 已完成
- [x] 实现 SubAgent 工具 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/subagent.py
  - **功能**:
    - `SubAgentTool`: 启动专用子代理处理复杂任务
    - `TaskTool`: 简化的自主任务启动接口
    - 代理类型: `explore`, `architect`, `coder`, `tester`, `general`
    - 每种类型都有专门的提示词
    - 支持 max_iterations 配置

- [x] 实现 Todo 工具 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/todo.py
  - **功能**:
    - `TodoWriteTool`: 创建和管理结构化任务列表
    - `TodoReadTool`: 读取待办列表，支持按状态筛选和多种格式输出
    - `TodoClearTool`: 清除已完成的待办或重置整个列表
    - `TodoList` 类: 完整的 CRUD 操作
    - 支持优先级 (high/medium/low) 和状态 (pending/in_progress/completed/cancelled)

- [x] 实现异步上下文管理器 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/utils/context.py
  - **功能**:
    - `AsyncContextManager`: 非阻塞上下文管理
    - 后台线程池用于 token 计数和压缩
    - `analyze_messages_async()`: 异步消息分析
    - `compress_messages_async()`: 异步压缩
    - `schedule_analysis()` / `schedule_compression()`: 即发即忘操作
    - `auto_compress_if_needed()`: 自动上下文管理
    - 缓存统计避免重复计算

- [x] 更新工具注册表 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/__init__.py
  - **新增导出**:
    - SubAgentTool, TaskTool
    - TodoWriteTool, TodoReadTool, TodoClearTool
  - **新增工厂函数**:
    - `create_registry_with_subagent()`: 包含 SubAgent 工具
    - `create_full_registry()`: 包含 SubAgent + MCP 工具
  - **更新**:
    - `create_default_registry()`: 现在包含 Todo 工具

### M10 阶段: CLI 参数增强 ✅ 已完成
- [x] 补充 CLI 全局参数 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/cli/main.py
  - **新增全局参数**:
    - `--max-iterations, -i`: 最大工具调用迭代次数 (默认: 100)
    - `--project, -P`: 项目目录 (默认: 当前目录)
    - `--config, -c`: 配置文件路径
    - `--yolo`: YOLO 模式 (允许读写系统任意文件)
    - `--debug-context`: 显示上下文 token 使用情况

- [x] 添加 max_iterations 配置项 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/config/schema.py
  - **ModelConfig 新增**:
    - `max_iterations`: 最大工具调用迭代次数 (默认: 100, 范围: 1-1000)

- [x] 在各命令中支持 max_iterations 参数 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/cli/chat.py, edit.py, task.py
  - **优先级**: CLI 参数 > 配置文件 > 默认值
  - **使用示例**:
    ```bash
    llc chat --max-iterations 50 "Complex task"
    llc -i 30 chat "Research topic"  # 使用全局参数
    llc edit src/app.py "Refactor" --max-iterations 20
    llc task "Big feature" -i 200
    ```

- [x] 更新 Agent 和 Orchestrator 支持 max_iterations - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/core/agent.py, orchestrator.py
  - `create_agent()` 新增 `max_iterations` 参数
  - `create_orchestrator()` 新增 `max_iterations` 参数

### M9 阶段: 上下文管理与 Token 追踪增强 ✅ 已完成
- [x] 实现上下文 Token 计数功能 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/utils/context.py
  - **功能**:
    - `estimate_tokens()`: 估算文本 token 数（支持中英文混合）
    - `count_message_tokens()`: 计算单条消息的 token 数
    - `count_messages_tokens()`: 计算消息列表总 token 数
    - `get_model_context_limit()`: 获取模型上下文限制
    - `MODEL_CONTEXT_LIMITS`: 各模型上下文限制映射表

- [x] 实现上下文统计和状态追踪 - 完成时间: 2024-12-11 - 负责人: maxazure
  - **ContextStats 类**:
    - 当前 token 数、最大 token 数
    - 各角色 token 分布 (system/user/assistant/tool)
    - 使用百分比、剩余 token 数
    - 警告状态 (near_limit > 80%, critical > 95%)

- [x] 实现上下文压缩机制 - 完成时间: 2024-12-11 - 负责人: maxazure
  - **ContextManager 类**:
    - `needs_compression()`: 检测是否需要压缩
    - `compress_messages()`: 执行消息压缩
    - 压缩策略: 保留 system prompt + 最近 N 条消息
    - 可配置阈值: `compression_threshold` (默认 80%)
    - 可配置保留比例: `retained_ratio` (默认 60%)

- [x] 集成到 Agent 和 CLI - 完成时间: 2024-12-11 - 负责人: maxazure
  - **Agent 类增强**:
    - `debug_context`: 调试模式显示上下文信息
    - `auto_compress`: 自动压缩功能
    - `get_context_stats()`: 获取上下文统计
    - `display_context_status()`: 显示上下文状态
  - **CLI chat 命令增强**:
    - `--debug-context` / `-dc`: 启用上下文调试输出
    - `/context` REPL 命令: 显示当前上下文统计
  - **调试输出格式**:
    ```
    ─── Iteration 1/10 ───
    Context Debug [glm-4.6]
    ├─ Total: 1,369/128,000 tokens (1.1%)
    ├─ Messages: 2
    ├─ System: 1,354 tokens
    ├─ User: 15 tokens
    ├─ Assistant: 0 tokens
    ├─ Tool: 0 tokens
    └─ Remaining: 126,631 tokens
    ```

- [x] 编写单元测试 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: tests/test_context.py (25 个测试用例)
  - 测试覆盖: token 估算、消息计数、模型限制、上下文统计、压缩机制

### M7.1 阶段: MCP CLI 增强 ✅ 已完成
- [x] `llc mcp list` 自动测试连接状态 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/cli/mcp_cmd.py
  - **功能**:
    - 自动测试所有已启用服务器的连接状态
    - 显示可用工具数量
    - 并发测试提高性能
    - `--no-test` 选项跳过测试
    - `-v` 详细模式显示错误信息
  - **测试**: tests/test_mcp.py (56 个测试用例)

### M6 阶段: CLI 增强 ✅ 已完成
- [x] 实现 Pipe Mode (-p) - 完成时间: 2024-12-10 - 负责人: maxazure
  - 支持命令: chat, edit, task
  - JSONL 格式输出，适合脚本集成
  - Tool calls 输出: `{"type": "tool_call", "tool": "...", "success": true, ...}`
  - Response 输出: `{"type": "response", "content": "...", "model": "...", "usage": {...}, "cost_usd": ...}`
  - 使用示例: `llc chat -p "What is Python?" | jq`

- [x] 添加 Help Option (-h) - 完成时间: 2024-12-10 - 负责人: maxazure
  - 所有命令支持 `-h` 和 `--help`
  - chat, edit, task, test, auth, config 等

### M5 阶段: GitHub Copilot 集成 ✅ 已完成
- [x] 实现 GitHub Copilot OAuth Device Flow 认证 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/auth/github_copilot.py
  - OAuth Device Flow 认证流程
  - 自动打开浏览器进行授权
  - Token 持久化存储 (~/.config/maxagent/copilot/token.json)
  
- [x] 实现 X-Initiator header 优化计费 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 解决 GitHub Copilot 重复计费问题
  - 首次消息使用 `X-Initiator: user`
  - 后续消息使用 `X-Initiator: agent`
  - 每个会话只计费一次 premium request

- [x] 实现 Copilot LLM Client - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/llm/copilot_client.py
  - CopilotLLMClient 类支持 GitHub Copilot API
  - 自动 token 刷新和管理
  - 集成 X-Initiator header 逻辑

- [x] 添加 CLI 认证命令 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/cli/auth_cmd.py
  - `llc auth copilot`: 进行 GitHub Copilot 认证
  - `llc auth status`: 查看所有 provider 认证状态
  - `llc auth logout copilot`: 登出并删除存储的凭证

- [x] 更新配置系统 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 添加 `github_copilot` provider 到 APIProvider 枚举
  - 支持环境变量 `GITHUB_COPILOT` 或 `USE_COPILOT`
  - 添加 Copilot 模型到 available_models 列表

- [x] 编写单元测试 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: tests/test_github_copilot.py (22 个测试用例)
  - Token 过期/有效性测试
  - CopilotSession X-Initiator 逻辑测试
  - 认证流程 mock 测试

- [x] 研究 LiteLLM + GitHub Copilot 集成方案 - 完成时间: 2024-12-09 - 负责人: maxazure
  - LiteLLM 原生支持 GitHub Copilot (`github_copilot/` 前缀)
  - 使用 OAuth Device Flow 认证
  - 支持 Tool Calling

- [x] 研究 Agent 框架选型 - 完成时间: 2024-12-09 - 负责人: maxazure
  - 对比了 LangChain、LangGraph、AutoGen、CrewAI
  - 结论: 选择原生实现，保持轻量和快速冷启动

- [x] 研究 CLI 框架选型 - 完成时间: 2024-12-09 - 负责人: maxazure
  - 对比了 Typer、Click、argparse
  - 结论: 选择 Typer + Rich 组合

- [x] 编写技术架构文档 - 完成时间: 2024-12-09 - 负责人: maxazure
  - 文件: docs/技术架构.md

- [x] 编写详细设计文档 - 完成时间: 2024-12-09 - 负责人: maxazure
  - 文件: docs/详细设计.md
  - 包含项目结构、API 设计、数据模型

### MVP 阶段 (M0) ✅ 已完成
- [x] 初始化项目结构 - 完成时间: 2024-12-09
- [x] 实现 LLM Client - 完成时间: 2024-12-09
- [x] 实现基础 Tool 系统 - 完成时间: 2024-12-09
- [x] 实现 chat 命令 - 完成时间: 2024-12-09
- [x] 实现 edit 命令 - 完成时间: 2024-12-09
- [x] 实现配置系统 - 完成时间: 2024-12-09

### M1 阶段: 多 Agent 支持 ✅ 已完成
- [x] 实现 Agent Orchestrator - 完成时间: 2024-12-09
  - 文件: src/maxagent/core/orchestrator.py
  - 支持多 Agent 协作工作流
  - 包含 TaskResult 数据模型
  
- [x] 实现 Architect Agent - 完成时间: 2024-12-09
  - 文件: src/maxagent/agents/architect.py
  - 负责需求分析和实现方案设计
  
- [x] 实现 Coder Agent - 完成时间: 2024-12-09
  - 文件: src/maxagent/agents/coder.py
  - 负责代码生成和修改
  
- [x] 实现 Tester Agent - 完成时间: 2024-12-09
  - 文件: src/maxagent/agents/tester.py
  - 负责测试生成和分析
  
- [x] 实现 task 命令 - 完成时间: 2024-12-09
  - 文件: src/maxagent/cli/task.py
  - 支持 --apply, --skip-tests, --skip-architect 等选项

### M2 阶段: 命令执行与 Git 工具 ✅ 已完成
- [x] 实现 run_command 工具 - 完成时间: 2024-12-09
  - 文件: src/maxagent/tools/command.py
  - 命令白名单机制
  - 用户确认机制
  - 输出截断
  - 超时保护

- [x] 实现 Git 工具 - 完成时间: 2024-12-09
  - 文件: src/maxagent/tools/git.py
  - git_status: 查看仓库状态
  - git_diff: 查看差异
  - git_log: 查看提交历史
  - git_branch: 查看分支

### OpenAI 兼容 API 支持 ✅ 已完成
- [x] 添加智谱 GLM API 支持 - 完成时间: 2024-12-10
  - 支持 OpenAI 兼容的 API 格式
  - 自动检测 API 端点路径
  - 环境变量: GLM_API_KEY, OPENAI_API_KEY
  - 默认使用 glm-4.6 模型
  - 端到端测试通过

### M2.5 阶段: 扩展工具与指令系统 ✅ 已完成
- [x] 实现指令文件加载器 - 完成时间: 2024-12-10
  - 文件: src/maxagent/core/instructions.py
  - 支持 MAXAGENT.md, AGENTS.md, CLAUDE.md 等指令文件
  - Progressive discovery: 遍历父目录发现指令文件
  - 全局指令文件: ~/.config/maxagent/MAXAGENT.md
  - InstructionsConfig 配置类

- [x] 实现 grep 工具 - 完成时间: 2024-12-10
  - 文件: src/maxagent/tools/grep.py
  - 支持正则表达式搜索
  - 优先使用 ripgrep (rg) 提高性能
  - 支持文件模式过滤

- [x] 实现 glob 工具 - 完成时间: 2024-12-10
  - 文件: src/maxagent/tools/glob.py
  - 支持 glob 模式匹配 (如 "**/*.py")
  - 按修改时间排序结果
  - 包含 find_files 工具

- [x] 实现 webfetch 工具 - 完成时间: 2024-12-10
  - 文件: src/maxagent/tools/webfetch.py
  - 获取 URL 内容并转换为文本/markdown
  - 支持缓存 (15分钟 TTL)
  - HTML 转换为纯文本或 Markdown

- [x] 实现 deep thinking 显示 - 完成时间: 2024-12-10
  - 文件: src/maxagent/utils/thinking.py
  - 解析 GLM <think>...</think> 标签
  - ThinkingStreamProcessor 支持流式处理
  - Rich Panel 显示思考过程

- [x] 更新配置系统 - 完成时间: 2024-12-10
  - 添加 InstructionsConfig 到 Config
  - 添加 thinking_model, enable_thinking, show_thinking 配置
  - 更新默认配置模板
  - 注册所有新工具到 ToolRegistry

### M3 阶段: 智能 Thinking 与指令集成 ✅ 已完成
- [x] 将指令加载器集成到 Agent - 完成时间: 2024-12-10
  - 文件: src/maxagent/core/agent.py
  - 在 create_agent() 中自动加载项目指令文件
  - 将指令内容合并到 system prompt
  
- [x] 实现智能 Thinking 策略选择器 - 完成时间: 2024-12-10
  - 文件: src/maxagent/core/thinking_strategy.py
  - 三种策略: auto, enabled, disabled
  - auto 模式根据问题复杂度自动判断是否使用 thinking 模型
  - 支持中英文关键词检测
  - 支持多步骤任务检测

- [x] 将 deep thinking 集成到 LLM Client - 完成时间: 2024-12-10
  - 文件: src/maxagent/llm/client.py, models.py
  - 支持 GLM glm-4.6 模型 (<think> 标签格式)
  - 支持 DeepSeek deepseek-reasoner 模型 (reasoning_content 字段)
  - 自动解析和分离 thinking 内容
  - thinking_content 和 reasoning_content 字段

- [x] 更新 CLI chat 命令 - 完成时间: 2024-12-10
  - 文件: src/maxagent/cli/chat.py
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
  - 文件: src/maxagent/cli/test_cmd.py
  - **测试框架检测**: 自动检测 pytest, unittest, jest, vitest, mocha, go test, cargo test
  - **测试执行**: 运行现有测试，支持 coverage 和 watch 模式
  - **测试生成**: 使用 AI (TesterAgent) 为指定文件生成测试
  - 子命令: detect, run, generate
  - 选项: --detect/-d, --run/-r, --generate/-g, --coverage/-c, --watch/-w, --verbose/-v

### M7 阶段: MCP (Model Context Protocol) 集成 ✅ 已完成
- [x] 实现 MCP 配置管理 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/mcp/config.py
  - **功能**:
    - MCPServerConfig: 服务器配置 (name, url, headers, type, env_vars)
    - MCPConfig: 配置容器
    - 环境变量替换: 支持 `${VAR}` 格式
    - 持久化存储: ~/.config/maxagent/mcp_servers.json

- [x] 实现 MCP HTTP 客户端 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/mcp/client.py
  - **功能**:
    - JSON-RPC 2.0 协议支持
    - Streamable HTTP 传输
    - SSE (Server-Sent Events) 响应处理
    - 会话管理 (Mcp-Session-Id)
    - 工具定义解析和调用

- [x] 实现 MCP Stdio 客户端 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/mcp/client.py
  - **功能**:
    - MCPStdioClient: 子进程 stdin/stdout 通信
    - 支持本地命令执行 (如 mcp-searxng)
    - 环境变量传递和替换
    - 异步响应读取
    - create_mcp_client() 工厂函数自动选择客户端类型

- [x] 实现 MCP 工具集成 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/mcp/tools.py
  - **功能**:
    - MCPTool: BaseTool 子类包装 MCP 工具
    - MCPToolRegistry: 全局 MCP 工具注册表
    - 自动转换为 OpenAI function schema
    - 集成到 Agent 工具系统

- [x] 实现 MCP CLI 命令 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/cli/mcp_cmd.py
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
  - 文件: tests/test_mcp.py (43 个测试用例)
  - 测试覆盖: 配置管理、HTTP 客户端、Stdio 客户端、工具定义、错误处理

- [x] 更新文档 - 完成时间: 2024-12-10 - 负责人: maxazure
  - docs/详细设计.md: 添加 MCP 模块 API 文档 (section 6.6)
  - docs/技术架构.md: 添加 MCP 架构描述 (section 10)
  - 更新测试覆盖率统计 (148 tests, 36%)

### M8 阶段: 提示词系统重构 ✅ 已完成
- [x] 实现新的结构化提示词系统 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/core/prompts.py
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
  - 更新 src/maxagent/core/agent.py: create_agent() 使用新提示词
  - 更新 src/maxagent/agents/architect.py: create_architect_agent() 使用新提示词
  - 更新 src/maxagent/agents/coder.py: create_coder_agent() 使用新提示词
  - 更新 src/maxagent/agents/tester.py: create_tester_agent() 使用新提示词
  - **特性**:
    - 所有 Agent 默认使用新的结构化提示词
    - 支持 `use_new_prompts=False` 回退到旧版提示词
    - 自动添加 grep/glob 工具到各 Agent
    - 自动注入项目指令文件 (MAXAGENT.md, CLAUDE.md 等)

- [x] 修复 write_file 工具路径安全问题 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/tools/file.py
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
    - src/maxagent/tools/__init__.py: `create_registry_with_mcp()` 支持 `allow_outside_project` 参数
    - src/maxagent/tools/file.py: SecurityChecker, ReadFileTool, WriteFileTool 支持 YOLO 模式
    - src/maxagent/core/orchestrator.py: Orchestrator 支持 `allow_outside_project` 参数
    - src/maxagent/core/prompts.py: 添加 `TOOL_USAGE_POLICY_YOLO` 提示词，移除路径限制说明
    - src/maxagent/core/agent.py: `create_agent()` 支持 `yolo_mode` 参数
    - src/maxagent/cli/chat.py: 添加 `--yolo` 选项
    - src/maxagent/cli/edit.py: 添加 `--yolo` 选项
    - src/maxagent/cli/task.py: 添加 `--yolo` 选项
  - **使用示例**:
    ```bash
    llc chat --yolo "Read ~/some/config.json"
    llc chat --yolo --no-think "Create a snake game in ~/snake_game"
    llc edit ~/some/file.py "Add docstrings" --yolo
    llc task "Update ~/config/settings.json" --yolo
    ```
  - **警告**: 启用 YOLO 模式会显示黄色警告提示
  - **注意**: 使用 `--no-think` 避免 GLM z1 thinking 模型的 tool_calls 兼容问题

## 📋 待办事项

### M12 阶段: 工具增强
- [x] WebFetch 工具增强 - 完成时间: 2024-12-11 - 负责人: maxazure
  - 文件: src/maxagent/tools/webfetch.py
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

- [ ] JavaScript 渲染支持 - 优先级: 低 - 预计工时: 6h
  - 使用 Playwright 或 Selenium
  - 需要额外依赖

### M4 阶段: 配置化与优化
- [ ] 完善配置系统 - 优先级: 低 - 预计工时: 2h
  - config init 命令 (已完成基础版)
  - config show 命令 (已完成)

- [x] 实现 Token 统计 - 完成时间: 2024-12-10 - 负责人: maxazure
  - 文件: src/maxagent/utils/tokens.py
  - **功能**:
    - 每次调用 token 用量追踪
    - 累计费用估算 (支持 GLM, OpenAI, DeepSeek 定价)
    - REPL 模式 `/tokens` 命令查看统计
    - 响应后显示当前调用 token 用量
  - **测试**: tests/test_tokens.py (18 个测试用例)

- [x] 实现多模型切换 - 完成时间: 2024-12-10 - 负责人: maxazure
  - **功能**:
    - REPL 模式 `/model` 查看当前模型
    - REPL 模式 `/model <name>` 切换模型
    - REPL 模式 `/models` 列出可用模型
    - 配置系统添加 `available_models` 列表
  - **支持环境变量**: GLM_API_KEY, ZHIPU_KEY (新增)

- [ ] 性能优化 - 优先级: 低 - 预计工时: 4h
  - 延迟导入
  - 缓存优化
  - 冷启动测试

- [x] 编写单元测试 - 完成时间: 2024-12-10 - 负责人: maxazure
  - tests/test_thinking_strategy.py: Thinking 策略选择器测试
  - tests/test_test_cmd.py: 测试命令和框架检测测试
  - tests/test_config_loader.py: 配置加载器测试
  - tests/test_tools_base.py: 工具基类测试
  - tests/test_tokens.py: Token 统计功能测试
  - tests/test_mcp.py: MCP 模块测试 (56 个测试用例，含连接状态测试)
  - tests/test_context.py: 上下文管理测试 (25 个测试用例)
  - 测试覆盖率: 36% (186 测试用例)

- [x] 端到端集成测试 (Snake Game) - 完成时间: 2024-12-10 - 负责人: maxazure
  - 测试目录: tests/e2e/snake_game_test/
  - **测试场景**: 使用 llc 生成 Snake 游戏
  - **测试结果**:
    - `llc task` 架构分析: 通过 - 正确生成实现计划
    - `llc chat` 工具调用: 通过 - read_file 工具正常工作
    - `llc chat --think` 深度思考: 部分通过 - 思考过程正常，输出格式需优化
    - Snake 游戏代码: 通过 - 语法正确，可正常导入

- [x] 端到端集成测试 (FastAPI) - 完成时间: 2024-12-10 - 负责人: maxazure
  - 测试目录: tests/e2e/fastapi_test/
  - **测试场景**: 多文件 FastAPI Todo API 项目
  - **项目结构**:
    - app/main.py: FastAPI 应用入口
    - app/models.py: Pydantic 模型 (Todo, TodoCreate, TodoUpdate)
    - app/database.py: 内存数据库模拟
    - app/routes/todos.py: CRUD 端点
    - requirements.txt: 依赖列表
  - **测试结果**:
    - `llc chat` 项目分析: 通过 - 正确读取和分析多个文件
    - FastAPI 应用导入: 通过
    - API 端点测试: 全部通过 (GET/POST/PUT/DELETE)
    - 404 错误处理: 通过

- [x] 修复已发现的问题 - 完成时间: 2024-12-10 - 负责人: maxazure
  - `llc edit` 命令: 修复 Typer 参数解析问题
  - GLM z1 thinking 模型 tool_calls: 添加嵌入式 JSON 解析处理
  - **注意**: GLM z1 模型在 tool_calls 场景下仍有兼容问题，建议使用 glm-4.6

## 🐛 已知问题

- [ ] GLM z1 thinking 模型 + tool_calls 兼容问题 - 发现时间: 2024-12-10
  - 问题: GLM z1 模型返回 tool_calls 时将整个 delta JSON 放入 content 字段
  - 影响: thinking 模式下工具调用可能失败
  - 临时方案: 使用 --no-think 或 glm-4.6 模型

## 💡 优化建议

- [x] 支持多模型配置和切换 - 完成时间: 2024-12-10 - 预期收益: 灵活性
- [x] 支持 MCP (Model Context Protocol) - 完成时间: 2024-12-10 - 预期收益: 扩展性
- [ ] 添加插件系统 - 提出时间: 2024-12-09 - 预期收益: 可扩展
- [ ] 支持 Web UI (可选) - 提出时间: 2024-12-09 - 预期收益: 用户体验

## 📚 学习笔记

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
| GLM | glm-4.6 | `<think>...</think>` 标签 | 内嵌在 content 中 |
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
# 4. Token 自动保存到 ~/.config/maxagent/copilot/token.json
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
╭───────────────────────────────── Assistant ──────────────────────────────────╮
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
- 配置文件: `~/.config/maxagent/mcp_servers.json`
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

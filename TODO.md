# MaxAgent 开发任务列表

## 🔄 进行中

*无当前进行中的任务*

## ✅ 最近完成

### CLI 重命名: llc → mcode ✅ 已完成
- [x] 重命名 CLI 命令和配置 - 完成时间: 2024-12-14
  - **CLI 命令**: `llc` → `mcode`
  - **配置目录**: `~/.llc/` → `~/.mcode/`
  - **项目配置**: `.llc.yaml` → `.mcode.yaml`
  - **环境变量**: `LLC_*` → `MCODE_*`
  - **修改文件**: 29 个文件 (源码、文档、测试)
  - **测试结果**: 349 测试全部通过

### 模型自动选择 Provider ✅ 已完成
- [x] 实现 --model 参数自动选择 provider - 完成时间: 2024-12-14
  - 从 `config.model.models` 动态读取 `provider/model` 配置
  - 移除硬编码的 `MODEL_PROVIDER_MAP`
  - 显示 `[Model: xxx | URL: xxx]` 信息

### M12.5 阶段: 多 Agent 协作修复 ✅ 已完成
- [x] 修复 subagent 调用失败问题 - 完成时间: 2024-12-13
  - **根本原因**: agent profiles 配置了 `model: github_copilot/gpt-4o`，但用户使用 GLM provider 且无 Copilot 认证
  - **解决方案**: 注释掉 agent profiles 中的 model 配置，使 subagent 使用主配置 provider
  - **错误处理改进**: `src/maxagent/tools/subagent.py` 添加详细的 401/403/timeout 错误诊断

- [x] 改进多 Agent 测试脚本 - 完成时间: 2024-12-13
  - 文件: `scripts/test_multiagent.sh`
  - **新特性**: 支持多种测试场景 (`simple`, `website`, `analyze`)
  - **日志统计**: Session 数量、工具调用统计、subagent 调用次数
  - **验证改进**: 更好的测试验证逻辑
  - **测试结果**: 3 个 Session，2 次 subagent 调用全部成功

### 配置文件目录统一 ✅ 已完成
- [x] 统一配置目录到 `~/.mcode` - 完成时间: 2024-12-13
  - **代码修改** (5 个文件):
    - `src/maxagent/auth/github_copilot.py`: `DEFAULT_TOKEN_DIR` → `~/.mcode/copilot`
    - `src/maxagent/mcp/config.py`: `get_mcp_config_path()` → `~/.mcode/mcp_servers.json`
    - `src/maxagent/config/schema.py`: `global_file` 默认值 → `~/.mcode/MAXAGENT.md`
    - `src/maxagent/config/loader.py`: 配置示例路径更新
    - `src/maxagent/core/instructions.py`: 文档注释路径更新
  - **文档更新** (3 个文件):
    - `TODO.md`: 5 处路径引用更新
    - `docs/详细设计.md`: 1 处路径引用更新
    - `scripts/start_litellm_copilot.py`: 帮助文本更新
  - **配置文件迁移**:
    - `~/.config/maxagent/copilot/token.json` → `~/.mcode/copilot/token.json`
    - `~/.config/maxagent/mcp_servers.json` → `~/.mcode/mcp_servers.json`

---

## 📋 待办事项

### M12 阶段: 工具增强
- [ ] JavaScript 渲染支持 - 优先级: 低 - 预计工时: 6h
  - 使用 Playwright 或 Selenium
  - 需要额外依赖

### M4 阶段: 配置化与优化
- [ ] 完善配置系统 - 优先级: 低 - 预计工时: 2h
  - config init 命令 (已完成基础版)
  - config show 命令 (已完成)

- [ ] 性能优化 - 优先级: 低 - 预计工时: 4h
  - 延迟导入
  - 缓存优化
  - 冷启动测试

---

## 🐛 已知问题

*无*

---

## 💡 优化建议

- [ ] 添加插件系统 - 提出时间: 2024-12-09 - 预期收益: 可扩展
- [ ] 支持 Web UI (可选) - 提出时间: 2024-12-09 - 预期收益: 用户体验

---

## 📚 快速参考

### 当前项目状态
- **测试覆盖率**: 50% (349 测试用例)
- **配置文件目录**: `~/.mcode/`
- **CLI 命令**: `mcode`
- **支持的 API Provider**: GLM, OpenAI, GitHub Copilot, LiteLLM, Custom
- **Thinking 模型**: GLM glm-4.6, DeepSeek deepseek-reasoner
- **MCP 协议**: 支持 HTTP 和 Stdio 两种传输方式

### 核心文件结构
```
src/maxagent/
├── core/          # 核心组件 (Agent, 指令, 思考策略)
├── agents/        # 专业化 Agent (架构师, 编码员, 测试员)
├── llm/          # LLM 客户端 (GLM, OpenAI, Copilot)
├── tools/        # 工具系统 (文件操作, 命令执行, Git 等)
├── cli/          # 命令行接口 (chat, edit, task, test, config, mcp, auth)
├── config/       # 配置系统 (加载器, 模式, agent profiles)
├── mcp/          # MCP 协议支持 (客户端, 配置, 工具)
├── auth/         # 认证模块 (GitHub Copilot OAuth)
└── utils/        # 工具函数 (上下文, token, 思考等)
```

### 最近完成的重要功能
1. **CLI 重命名**: `llc` → `mcode`，配置目录 `~/.llc/` → `~/.mcode/`
2. **模型自动选择**: `--model` 参数自动选择正确的 provider
3. **多 Agent 协作**: 修复了 subagent 调用失败问题
4. **配置目录统一**: 从 `~/.config/maxagent/` 迁移到 `~/.mcode/`
5. **MCP 集成**: 完整的 Model Context Protocol 支持
6. **Thinking 系统**: 智能思考策略和深度思考功能
7. **测试框架**: 智能测试检测和生成功能

---

**详细开发历史请参考 [TODO-history.md](TODO-history.md) 文件**
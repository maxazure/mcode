# MaxAgent Copilot 指令

- **项目目标**：这是一个 AI Code Agent 的程序。入口：[src/maxagent/cli/main.py](src/maxagent/cli/main.py)。

- **项目结构**：
  - 根文件：`README.md`、`pyproject.toml`（打包与依赖）、`TODO.md`、`docs/`（架构与设计文档）、`scripts/`（辅助脚本）。
  - 源码：`src/maxagent/`
    - `cli/`：命令入口与子命令（`main.py`, `chat.py`, `edit.py`, `task.py`, `test_cmd.py`, `auth_cmd.py`, `mcp_cmd.py`）
    - `core/`：Agent 基类、`orchestrator.py`、`prompts.py`、流程控制与指令辅助（`agent.py`, `orchestrator.py`, `thinking_strategy.py`）
    - `agents/`：专门化 agent 实现（`architect.py`, `coder.py`, `tester.py`）
    - `tools/`：工具实现与注册（`registry.py`, `file.py`, `edit.py`, `command.py` 等），以及 `create_default_registry` / `create_full_registry` 工厂
    - `llm/`：LLM 客户端抽象、Copilot adapter、工厂（`factory.py`, `client.py`, `copilot_client.py`）
    - `mcp/`：MCP 客户端、配置与工具（`client.py`, `config.py`, `tools.py`）
    - `auth/`：Copilot OAuth（`auth/github_copilot.py`）
    - `config/`：配置加载与 schema（`loader.py`, `schema.py`）
    - `utils/`：辅助函数（`diff.py`, `context_summary.py`, `tokens.py`, `console.py`）
  - `tests/`：单元与端到端测试，示例 `tests/e2e`（`fastapi_test`, `snake_game_test`）
    - e2e 测试输出约定：运行端到端测试时，请将所有由测试或 Agent 生成的临时/输出文件统一写入 `tests/e2e/_output/`（或 `tests/e2e/tmp/`）。CI 或测试脚本可在测试后统一清理该目录，且建议将其加入 `.gitignore`，避免意外提交。
- **配置优先级**（从高到低）：环境变量 -> 项目 [.llc.yaml](.llc.yaml) -> 用户配置 [~/.llc/config.yaml](~/.llc/config.yaml) -> 默认值。环境变量优先链：GLM_API_KEY/ZHIPU_KEY > OPENAI_API_KEY > LITELLM_API_KEY > GITHUB_COPILOT（可被 LLC_PROVIDER/MAXAGENT_PROVIDER 或 GITHUB_COPILOT/USE_COPILOT 强制覆盖）；通过 `LLC_MODEL/MAXAGENT_MODEL` 强制模型，`LITELLM_BASE_URL/OPENAI_BASE_URL` 可覆盖 base URL。详见 [src/maxagent/config/loader.py](src/maxagent/config/loader.py#L1-L214)。

- **快速上手命令**：
  - 安装：```
    python -m venv .venv
    source .venv/bin/activate
    pip install -e .
    ```
  - 运行：`llc chat "..."`, `llc edit <file> "..."`, `llc task "..."`；Copilot 登录：`llc auth copilot`（或首次调用时自动 Device Flow）。
- **补丁/编辑约定**：补丁使用 unified diff，并放在 ```diff 代码块中；请在补丁之前说明变更意图，补丁中保留 2-3 行上下文行，路径以 `a/...` 和 `b/...` 表示（见 `EDIT_SYSTEM_PROMPT`）。
- **性能/搜索优先级**：优先使用内置搜索工具（`search_code`/`grep`/`glob`/`find_files`）定位相关文件，再使用 `read_file` 获取具体内容以减少无谓的读取与 token 消耗。对外脚本或程序化调用，使用 `--pipe` 并由 JSONL 流解析结果。

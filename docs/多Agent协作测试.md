# 多 Agent 协作测试

本文档记录多 Agent 协作场景的测试方案，以企业网站开发为例。

## Agent 配置文件

已在 `~/.llc/agents/` 目录下创建以下专业 Agent：

| Agent 文件 | 角色 | 职责 |
|-----------|------|------|
| `general.md` | 通用 Agent | 根据任务自动识别角色并执行 |
| `web_pm.md` | 项目经理 | 需求分析、任务分配、进度协调 |
| `web_designer.md` | 设计师 | UI/UX 设计、配色方案、布局规划 |
| `web_frontend.md` | 前端工程师 | HTML/CSS/JS 代码实现 |
| `web_content.md` | 内容策划 | 文案撰写、SEO 优化 |
| `web_qa.md` | 质量测试 | 代码检查、可访问性、性能 |

## 快速测试

```bash
# 运行测试脚本
./scripts/test_multiagent.sh

# 或手动执行
llc chat --trace "请使用 subagent 创建企业网站"
```

## 测试场景 1: 自动调用 SubAgent

### 提示词设计（推荐方式）

由于 `agent_type` 参数只支持内置的 6 种类型，自定义 agent 需要通过 `general` 类型 + task 描述角色来实现：

```
请为一家名为"云智科技"的人工智能公司创建企业官网。

公司信息：
- 行业：人工智能/机器学习
- 核心业务：AI 解决方案、数据分析、智能客服
- 目标客户：中大型企业
- 网站风格：专业、科技感、简洁

请按以下步骤使用 subagent 完成：

1. 调用 subagent(agent_type="general", task="作为网站内容策划师，生成网站文案...")
2. 调用 subagent(agent_type="general", task="作为前端工程师，创建 HTML 页面...")
3. 调用 subagent(agent_type="general", task="作为 CSS 设计师，创建样式文件...")

输出目录：demo/enterprise_website/
```

### 测试命令

```bash
# 基础测试
llc chat "请为一家名为云智科技的AI公司创建企业官网，使用subagent分别调用web_content、web_designer、web_frontend完成"

# 带调试日志
MAXAGENT_DEBUG_LOG=/tmp/multiagent_test.log llc chat --trace "请为一家名为云智科技的AI公司创建企业官网，使用subagent分别调用web_content、web_designer、web_frontend完成"
```

## 测试场景 2: 自动协作链

### 提示词设计（让主 Agent 自动判断并调用）

```
请创建一个完整的企业网站。

企业信息：
- 名称：绿源环保科技
- 行业：环保技术
- 业务：污水处理、空气净化、环境监测

请自动规划任务，调用合适的专业 agent（web_content、web_designer、web_frontend）完成网站开发。
所有文件输出到 demo/green_tech_website/ 目录。
```

## 测试场景 3: 并行 SubAgent

### 提示词设计（测试并行能力）

```
我需要同时为三个页面准备内容：
1. 首页内容
2. 关于我们页面内容  
3. 联系我们页面内容

请并行调用 3 个 subagent(agent_type="general") 分别生成这三个页面的内容。
```

## 测试场景 4: 完整工作流（含 QA）

```
请为"智联健康"医疗科技公司创建企业官网，完整工作流程：

1. 【内容策划】调用 web_content agent 生成网站文案
2. 【视觉设计】调用 web_designer agent 设计样式方案
3. 【代码实现】调用 web_frontend agent 编写代码
4. 【质量检查】调用 web_qa agent 检查代码质量

输出目录：demo/health_tech_website/
```

## Agent 配置示例

### ~/.llc/agents/web_designer.md
```markdown
---
model: github_copilot/gpt-4o
---

# 网站设计师 (Web Designer Agent)

你是一名专业的网站 UI/UX 设计师...
```

## 预期行为

1. 主 Agent 收到任务后，分析需求
2. 调用 `subagent(agent_type="general", task="...")` 工具
3. SubAgent 加载对应的 `~/.llc/agents/<name>.md` 配置
4. SubAgent 执行任务并返回结果
5. 主 Agent 汇总结果，继续下一步

## 验证要点

- [ ] SubAgent 配置文件被正确加载
- [ ] 专业提示词被应用到 SubAgent
- [ ] SubAgent 间可以传递上下文
- [ ] 最终输出完整的网站文件
- [ ] trace 日志显示调用链路

## 调试技巧

```bash
# 查看 agent 配置是否被加载
cat ~/.llc/agents/web_designer.md

# 查看调试日志
tail -f /tmp/multiagent_test.log

# 验证输出文件
ls -la demo/enterprise_website/
```

## 注意事项

1. 当前 subagent 的 `agent_type` 参数是枚举值（explore/architect/coder/tester/shell/general）
2. 自定义 agent（如 web_designer）需要使用 `agent_type="general"`，然后在 task 中指明角色
3. 或者需要扩展 subagent.py 支持自定义 agent_type

## 当前实现机制

基于代码分析，自定义 agent profile 的工作方式如下：

1. **agent_type 映射**: SubAgent 支持 6 种内置类型：`explore`, `architect`, `coder`, `tester`, `shell`, `general`
2. **profile 加载**: 通过 `_apply_profile_prompt()` 从 `~/.llc/agents/<agent_type>.md` 加载自定义提示词
3. **自定义 agent**: 使用 `agent_type="general"`，然后在 **task 参数中指明角色**

### 实际调用方式

```python
# 调用自定义 web_designer agent 的正确方式
subagent(
    agent_type="general",  # 使用 general 类型
    task="请作为 web_designer 角色，为云智科技设计网站视觉方案",
    context="这是一家 AI 公司，需要专业、科技感的设计风格"
)
```

### general 类型的特性

- 拥有所有工具访问权限（`tools=[]` 表示全部工具）
- 会加载 `~/.llc/agents/general.md` 配置（如存在）
- temperature=0.5（较灵活的创造性）
- 适合各类自定义任务

## 扩展方案（可选）

如果希望支持直接使用自定义 agent_type 名称，可以修改：

```python
# src/maxagent/tools/subagent.py - _map_agent_type_to_profile_name()
def _map_agent_type_to_profile_name(self, agent_type: str) -> str:
    # 如果 ~/.llc/agents/<agent_type>.md 存在，直接使用
    from pathlib import Path
    custom_path = Path.home() / ".llc" / "agents" / f"{agent_type}.md"
    if custom_path.exists():
        return agent_type
    # 否则使用内置映射
    mapping = {
        "explore": "explore",
        "architect": "architect",
        # ...
    }
    return mapping.get(agent_type, agent_type or "general")
```

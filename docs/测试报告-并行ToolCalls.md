# glm-4.6 并行 Tool Calls 测试报告

**测试时间**: 2025年12月13日
**模型**: glm-4.6
**测试目的**: 评估不同提示词对模型返回多个 tool_calls 的影响

---

## 🎯 优化效果验证（批量编辑测试）

### 测试场景
为 `calculator.py` 中的 9 个函数添加 Google 风格 docstring

### 优化结果

| 指标 | 优化前（推测） | 优化后（实测） |
|------|---------------|---------------|
| edit 调用次数 | 9-15+ 次 | **1 次** |
| 总请求数 | 10-20 次 | **3 次** |
| Token 消耗 | ~50K+ | **~18K** |
| 使用 batched edits | ❌ | ✅ (9 items) |

### Debug 日志证明

```json
[Request 2] LLM_RESPONSE
{
  "tool_calls": [
    {
      "name": "edit",
      "args_summary": {
        "file_path": "tests/e2e/calculator.py",
        "edits": "[9 items]"  // ✅ 一次批量编辑包含 9 个修改
      }
    }
  ]
}
```

---

## 📊 测试结果汇总

- **成功的测试**: 7/7
- **返回多个 tool_calls 的测试**: 5/7
- **并行成功率**: **71.4%**

## ✅ 有效的提示词变体 (5个)

这些提示词能够成功触发 glm-4.6 一次返回 3 个 tool_calls：

### 1. baseline - 简单任务列表
```
请执行以下任务：
1. 读取 game.py 文件
2. 读取 config.py 文件
3. 读取 utils.py 文件

请立即执行这些操作。
```
✅ **返回 3 个 tool_calls** | finish_reason: tool_calls

### 2. explicit_parallel - 明确要求并行
```
请执行以下任务：
1. 读取 game.py 文件
2. 读取 config.py 文件  
3. 读取 utils.py 文件

重要：请在一个响应中同时调用所有三个 read_file 工具，不要分多次请求。
```
✅ **返回 3 个 tool_calls** | finish_reason: tool_calls

### 3. efficiency_warning - 效率警告
```
⚠️ 效率规则：为了减少请求次数，当需要多个独立的工具操作时，
必须在同一个响应中包含所有工具调用。

任务：
1. 读取 game.py 文件
2. 读取 config.py 文件
3. 读取 utils.py 文件

请在一个响应中完成所有文件读取。
```
✅ **返回 3 个 tool_calls** | finish_reason: tool_calls

### 4. strong_command - 强命令式
```
🚨 必须遵守的规则：
- 当有多个独立的工具操作时，必须在一个响应中返回所有 tool_calls
- 禁止为同一组任务发送多个请求

现在请读取以下三个文件：game.py, config.py, utils.py

你必须在一个响应中调用所有三个 read_file。
```
✅ **返回 3 个 tool_calls** | finish_reason: tool_calls

### 5. numbered_list - 数字步骤列表
```
请按以下步骤操作：

步骤1: 读取 game.py
步骤2: 读取 config.py  
步骤3: 读取 utils.py

这些是独立的操作，可以并行执行。请在一个响应中完成所有步骤。
```
✅ **返回 3 个 tool_calls** | finish_reason: tool_calls

---

## ❌ 无效的提示词变体 (2个)

### 6. code_example - 代码示例
```
任务：读取三个文件：game.py, config.py, utils.py

示例：正确的做法是在一个响应中调用多个工具：
\`\`\`
tool_calls: [
  {"name": "read_file", "arguments": {"path": "game.py"}},
  {"name": "read_file", "arguments": {"path": "config.py"}},
  {"name": "read_file", "arguments": {"path": "utils.py"}}
]
\`\`\`

请按照上述方式执行。
```
❌ **返回 0 个 tool_calls** | finish_reason: stop
📝 模型把示例当成了最终输出，直接返回了代码块文本而不是实际调用工具

### 7. batch_edit_test - 批量编辑参数
```
请对 game.py 文件进行以下修改：
1. 将 SPEED = 5 改为 SPEED = 10
2. 将 MAX_PLAYERS = 2 改为 MAX_PLAYERS = 4
3. 将 DEBUG = False 改为 DEBUG = True

重要：使用 edit 工具的 edits 参数来批量执行这些修改。
```
❌ **返回 1 个 tool_calls** | finish_reason: tool_calls
📝 模型先调用 read_file，没有直接使用 edit 的 edits 参数

---

## 🔍 关键发现

### ✅ 有效策略

1. **简单任务列表最有效** - baseline 变体无需特殊指令即可触发并行调用
2. **明确指令有帮助** - explicit_parallel、efficiency_warning 增强了并行意图
3. **强命令语气有效** - strong_command 的 emoji 和强制语气也能触发
4. **数字步骤格式有效** - numbered_list 清晰表达了并行性

### ❌ 失败原因分析

1. **代码示例反作用** - 模型可能将示例代码理解为期望的输出格式而非执行指令
2. **批量参数理解不足** - 模型没有理解 `edits` 参数的批量编辑用途，选择了保守的 read-then-edit 策略

### 📈 并行成功率: 71.4%

对于读取文件这种独立操作，glm-4.6 在大多数情况下能够正确识别并行机会。

---

## 💡 建议

### 对于 MaxAgent 系统 Prompt

1. **采用 baseline 风格** - 简单明了的任务列表即可，无需过度强调
2. **保留效率警告** - 在 TOOL_USAGE_POLICY 开头的效率规则仍然有价值
3. **避免代码示例** - 不要在 prompt 中展示 tool_calls 的 JSON 格式，模型可能混淆
4. **明确说明批量参数** - 对于 `edit` 工具的 `edits` 参数，需要更清晰的说明和示例

### 改进建议

当前 MaxAgent 的 TOOL_USAGE_POLICY 已经很好，建议微调：

```markdown
## ⚠️ 效率规则

当需要多个独立的工具操作时（如读取多个文件），在一个响应中返回所有 tool_calls。

示例任务：读取 a.py、b.py、c.py
正确做法：在一个响应中调用 3 次 read_file
错误做法：分 3 个请求分别调用
```

**关键**：避免给出 JSON 格式示例，直接用自然语言描述即可。

---

## 📁 测试文件

- 测试脚本: `scripts/test_parallel_tool_calls.py`
- 测试结果: `/tmp/parallel_results.json`
- 使用方法: `python scripts/test_parallel_tool_calls.py --demo` (查看所有提示词)

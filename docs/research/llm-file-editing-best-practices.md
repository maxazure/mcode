# LLM Agent 文件编辑最佳实践研究报告

## 研究日期: 2025年12月11日

## 研究来源

1. **Anthropic Text Editor Tool** - Claude 官方文档
2. **OpenAI Function Calling** - 最佳实践指南
3. **Aider** - Chat Modes 和 Edit Formats
4. **OpenCode** - SST 的 AI 编码助手
5. **Cline** - VS Code AI 编码扩展

---

## 1. Anthropic Text Editor Tool 设计

### 核心命令
Anthropic 设计了一个专用的 `str_replace_based_edit_tool`，支持以下命令：

| 命令 | 用途 | 关键参数 |
|------|------|----------|
| `view` | 查看文件或目录内容 | path, view_range (行范围) |
| `str_replace` | 精确替换字符串 | path, old_str, new_str |
| `create` | 创建新文件 | path, file_text |
| `insert` | 在指定行插入文本 | path, insert_line, new_str |

### 关键设计原则

1. **先查看后编辑**: Claude 会先使用 `view` 命令查看文件内容，然后再进行编辑
2. **精确匹配**: `old_str` 必须完全匹配文件内容（包括空格和缩进）
3. **唯一匹配**: 替换必须匹配且仅匹配一处位置
4. **行号辅助**: view 结果包含行号前缀，帮助定位
5. **错误处理**: 明确处理 "未找到"、"多处匹配"、"权限错误" 等情况

### 实现建议
```python
# 返回结果应包含行号
"1: def is_prime(n):\n2:     \"\"\"Check if a number is prime.\"\"\"\n3:     if n <= 1:"

# 成功替换返回
"Successfully replaced text at exactly one location."
```

---

## 2. OpenAI Function Calling 最佳实践

### 函数定义最佳实践

1. **清晰的描述**: 写明确的函数名称、参数描述和说明
2. **使用枚举**: 用 enum 限制参数值，避免无效状态
3. **Strict Mode**: 启用 `strict: true` 确保参数格式正确
4. **函数数量**: 保持工具数量 < 20 个
5. **软件工程原则**: 遵循最小惊讶原则

### 关键配置
```json
{
  "type": "function",
  "name": "edit_file",
  "strict": true,
  "parameters": {
    "type": "object",
    "properties": {
      "file_path": {"type": "string"},
      "old_string": {"type": "string"},
      "new_string": {"type": "string"}
    },
    "required": ["file_path", "old_string", "new_string"],
    "additionalProperties": false
  }
}
```

### 并行工具调用
- 支持多个工具同时调用
- 可通过 `parallel_tool_calls: false` 禁用

---

## 3. Aider 的编辑模式设计

### Ask/Code 工作流
1. **Ask 模式**: 讨论方案，获取建议
2. **Code 模式**: 执行实际编辑
3. **优势**: 分离讨论和执行，减少错误

### Architect 模式（双模型）
1. **Architect 模型**: 规划如何解决问题（可用 o1 等推理模型）
2. **Editor 模型**: 将规划转换为具体编辑指令（如 GPT-4o）
3. **优势**: 让推理模型专注规划，编辑模型专注执行

### 编辑格式
| 格式 | 描述 | 适用场景 |
|------|------|----------|
| `whole` | 返回完整文件 | 简单但低效 |
| `diff` | SEARCH/REPLACE 块 | 高效精确 |
| `diff-fenced` | 带围栏的 diff | Gemini 模型 |
| `udiff` | 统一 diff 格式 | GPT-4 Turbo |

### Diff 格式示例
```
mathweb/flask/app.py
import math
from flask import Flask

```

---

## 4. OpenCode 的实现细节

### 多层替换策略
OpenCode 实现了多个 Replacer（与 MaxAgent 类似），按顺序尝试：

1. **SimpleReplacer** - 精确匹配
2. **LineTrimmedReplacer** - 行尾空格容错
3. **BlockAnchorReplacer** - 首尾行锚定 + 相似度
4. **WhitespaceNormalizedReplacer** - 空格标准化
5. **IndentationFlexibleReplacer** - 缩进灵活
6. **EscapeNormalizedReplacer** - 转义字符处理
7. **TrimmedBoundaryReplacer** - 边界空格处理
8. **ContextAwareReplacer** - 上下文感知
9. **MultiOccurrenceReplacer** - 多处匹配（配合 replaceAll）

### 关键工具提示
```
edit.txt 核心提示：
- 必须先用 Read 工具读取文件
- oldString 必须精确匹配（包括空格和缩进）
- 如果找到多处匹配，提供更多上下文
- 使用 replaceAll 进行全局替换
```

### 强制先读后写
```
write.txt:
- 如果是已存在的文件，必须先用 Read 工具读取
- 优先编辑现有文件，不要创建新文件
```

---

## 5. Cline 的实现细节

### 双工具设计
Cline 提供两个文件操作工具：

| 工具 | 用途 | 何时使用 |
|------|------|----------|
| `write_to_file` | 创建/覆盖文件 | 新建文件、大规模重写 |
| `replace_in_file` | SEARCH/REPLACE 编辑 | 小范围精确修改 |

### 选择策略
```markdown
**默认使用 replace_in_file** - 更安全、更精确
**使用 write_to_file** 当：
- 创建新文件
- 变更太多导致 replace_in_file 复杂或易错
- 需要完全重组文件结构
- 文件较小且大部分内容需要修改
```

### SEARCH/REPLACE 格式
```
------- SEARCH
[exact content to find]
=======
[new content to replace with]
+++++++ REPLACE
```

### 关键规则
1. SEARCH 内容必须精确匹配（字符、空格、缩进、换行）
2. 多个 SEARCH/REPLACE 块可以在单次调用中
3. 每个块只替换第一次匹配
4. 移动代码：用两个块（删除原位置 + 插入新位置）

### Auto-formatting 处理
- 编辑后编辑器可能自动格式化
- 工具返回最终文件状态
- 后续编辑使用返回的最终状态作为参考

---

## 6. 当前问题分析

根据用户反馈，MaxAgent 存在以下问题：

### 6.1 不执行编辑
**可能原因**:
- 工具描述不够清晰
- 提示词中何时使用哪个工具不明确
- 模型倾向于解释而非执行

**解决方案**:
- 参考 Aider 的 ask/code 模式区分
- 更明确的工具选择指导
- 强调 "执行" 而非 "建议"

### 6.2 缩进错误
**可能原因**:
- old_string 匹配时未考虑上下文缩进
- new_string 缩进与位置不匹配
- 替换策略过于宽松

**解决方案**:
- 强调在提示词中保持精确缩进
- 添加缩进验证逻辑
- 返回编辑后的文件片段供模型确认

### 6.3 覆盖代码
**可能原因**:
- 使用 write_file 时未保留原有代码
- 模型记忆原文件内容不准确

**解决方案**:
- **强制先读后写**: 编辑前必须先 read_file
- 添加文件时间戳检查（如 OpenCode）
- write_file 时检测是否遗漏了原有函数

---

## 7. 改进建议

### 7.1 工具层面

#### A. 添加 FileTime 检查
```python
# 记录文件读取时间，编辑时验证
class FileTime:
    read_times: dict[str, float] = {}
    
    @classmethod
    def read(cls, session_id: str, file_path: str):
        cls.read_times[f"{session_id}:{file_path}"] = time.time()
    
    @classmethod
    def assert_read(cls, session_id: str, file_path: str):
        key = f"{session_id}:{file_path}"
        if key not in cls.read_times:
            raise ValueError(f"Must read {file_path} before editing")
```

#### B. 返回最终文件内容
```python
# 编辑成功后返回
return ToolResult(
    success=True,
    output=f"Successfully edited {file_path}",
    metadata={
        "diff": diff_output,
        "final_content": final_content[:1000],  # 截断
        "diagnostics": diagnostics  # LSP 诊断信息
    }
)
```

#### C. 增强错误消息
```python
if not_found:
    raise ValueError(
        f"oldString not found in content. "
        f"This is likely because the SEARCH block doesn't match exactly. "
        f"Please verify whitespace and indentation match the file exactly."
    )

if multiple_matches:
    raise ValueError(
        f"Found {count} matches for oldString. "
        f"Provide more surrounding context to uniquely identify the location."
    )
```

### 7.2 提示词层面

#### A. 强化工具选择指导
```markdown
## 文件编辑决策树

1. 你要编辑的是新文件还是已存在的文件?
   - 新文件 → 使用 write_file
   - 已存在 → 继续步骤 2

2. 你已经读取过这个文件了吗?
   - 没有 → 先用 read_file 读取
   - 是的 → 继续步骤 3

3. 变更的范围有多大?
   - 小范围（<10 行，修复/重命名/添加注释）→ edit 工具
   - 中等（添加新函数但保留其他）→ 考虑多个 edit 或谨慎使用 write_file
   - 大范围（>50% 变更）→ write_file

4. 使用 write_file 时务必:
   - 包含所有原有代码（复制粘贴）
   - 仅添加/修改需要变更的部分
```

#### B. 编辑工具详细说明
```markdown
### edit 工具使用要点

**参数说明**:
- `file_path`: 文件路径
- `old_string`: 要替换的精确内容（必须与文件完全匹配）
- `new_string`: 替换后的内容
- `replace_all`: 是否替换所有匹配（默认 false）

**关键规则**:
1. old_string 必须是文件中的精确内容，包括:
   - 所有空格和制表符
   - 正确的缩进
   - 换行符
   
2. 如果编辑失败并显示 "multiple matches"，添加更多上下文行

3. 如果编辑失败并显示 "not found"，使用 read_file 重新获取内容

**示例**:
```
# 好的例子 - 包含足够上下文
edit(
    file_path="src/app.py",
    old_string="def process_data(items):\n    results = []\n    for item in items:",
    new_string="def process_data(items):\n    \"\"\"Process a list of items.\"\"\"\n    results = []\n    for item in items:"
)

# 坏的例子 - 可能有多处匹配
edit(
    file_path="src/app.py",
    old_string="return result",  # 太短，可能多处匹配
    new_string="return result or default"
)
```
```

### 7.3 架构层面

#### A. 考虑 Architect/Editor 双模式
```python
# 可选的架构师模式
class ArchitectMode:
    """
    1. 用户请求发送给 architect_model（如 o1）
    2. architect 返回纯文本计划
    3. 计划发送给 editor_model（如 GPT-4o）
    4. editor 生成具体的工具调用
    """
    pass
```

#### B. 编辑验证步骤
```python
async def edit_with_validation(file_path, old_string, new_string):
    # 1. 执行编辑
    result = await edit_file(file_path, old_string, new_string)
    
    # 2. 验证结果
    new_content = await read_file(file_path)
    
    # 3. 运行 LSP 诊断
    diagnostics = await get_diagnostics(file_path)
    
    # 4. 如果有错误，可以自动回滚
    if has_critical_errors(diagnostics):
        await revert(file_path)
        raise EditValidationError(diagnostics)
    
    return result
```

---

## 8. 实施优先级

### 高优先级（立即实施）
1. ✅ 强化提示词中的 "先读后写" 规则
2. ✅ 改进 edit 工具的错误消息
3. ✅ 添加更详细的工具使用示例

### 中优先级（近期）
1. 添加 FileTime 检查强制先读后写
2. 返回编辑后的文件内容片段
3. 添加缩进验证逻辑

### 低优先级（长期）
1. 考虑 Architect/Editor 双模式
2. 添加 LSP 诊断集成
3. 实现自动回滚机制

---

## 9. 参考链接

- [Anthropic Text Editor Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool)
- [OpenAI Function Calling](https://platform.openai.com/docs/guides/function-calling)
- [Aider Chat Modes](https://aider.chat/docs/usage/modes.html)
- [Aider Edit Formats](https://aider.chat/docs/more/edit-formats.html)
- [OpenCode GitHub](https://github.com/sst/opencode)
- [Cline GitHub](https://github.com/cline/cline)

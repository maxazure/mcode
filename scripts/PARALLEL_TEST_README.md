# GLM-4.6 并行 Tool Calls 测试

测试 glm-4.6 模型在不同提示词下返回多个 tool_calls 的能力。

## 快速开始

```bash
# 方法 1: 使用环境变量
export GLM_API_KEY="your-api-key"
python scripts/test_parallel_tool_calls.py -v

# 方法 2: 传递 API key
python scripts/test_parallel_tool_calls.py -v --api-key "your-api-key"

# 方法 3: 保存结果到文件
python scripts/test_parallel_tool_calls.py -v -o results.json
```

## 测试内容

脚本包含 7 种不同的提示词变体来测试模型是否能一次返回多个 tool_calls：

1. **baseline** - 基础提示词
2. **explicit_parallel** - 明确要求并行调用
3. **efficiency_warning** - 带效率警告的提示
4. **code_example** - 提供代码示例
5. **batch_edit_test** - 测试批量编辑
6. **strong_command** - 强烈命令式指导
7. **numbered_list** - 数字列表式任务

## 输出示例

```
======================================================================
测试 glm-4.6 模型的并行 tool_calls 能力
======================================================================

模型: glm-4.6
Base URL: https://open.bigmodel.cn/api/coding/paas/v4
parallel_tool_calls 配置: True

总共 7 个测试变体

[1/7] 测试变体: baseline
------------------------------------------------------------
返回的 tool_calls 数量: 1
Tool calls:
  1. read_file({"path": "game.py"})
是否并行: ❌ 否

...

======================================================================
测试结果汇总
======================================================================

成功的测试: 7/7
返回多个 tool_calls 的测试: 2/7
并行成功率: 28.6%

✅ 能够触发并行 tool_calls 的提示词变体:
  - code_example (返回 3 个调用)
  - strong_command (返回 3 个调用)
```

## 自定义测试

编辑脚本中的 `PROMPT_VARIANTS` 字典来添加你自己的提示词变体：

```python
PROMPT_VARIANTS = {
    "your_variant": """你的提示词内容...""",
    # ...
}
```

## 分析结果

结果会显示：
- 每个变体返回的 tool_calls 数量
- 是否实现并行调用
- 并行成功率统计
- 最有效的提示词变体

用这个工具来优化你的 prompt，提高 tool calling 效率！

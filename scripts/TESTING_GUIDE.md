# 测试脚本使用说明

我已创建了一个测试脚本来评估 glm-4.6 模型在不同提示词下的并行 tool_calls 能力。

## 📁 文件位置

- 主脚本: `scripts/test_parallel_tool_calls.py`
- 说明文档: `scripts/PARALLEL_TEST_README.md`
- Shell 包装: `scripts/run_parallel_test.sh`

## 🚀 快速开始

### 1. 查看所有测试提示词（演示模式）

```bash
python scripts/test_parallel_tool_calls.py --demo
```

这会展示所有 7 种提示词变体，无需 API key。

### 2. 运行实际测试

```bash
# 使用 API key
python scripts/test_parallel_tool_calls.py --api-key "your-glm-api-key" -v

# 或使用环境变量
export GLM_API_KEY="your-api-key"
python scripts/test_parallel_tool_calls.py -v

# 保存结果
python scripts/test_parallel_tool_calls.py -v -o results.json
```

## 📊 测试的 7 种提示词变体

1. **baseline** - 简单的任务列表
2. **explicit_parallel** - 明确要求并行执行
3. **efficiency_warning** - 效率警告 + 任务
4. **code_example** - 提供具体代码示例
5. **batch_edit_test** - 测试批量编辑参数
6. **strong_command** - 强命令 + emoji 警告
7. **numbered_list** - 数字步骤列表

## 🎯 测试目的

验证不同提示词策略对 glm-4.6 返回多个 tool_calls 的影响，找出最有效的提示方式。

## 📈 输出内容

- 每个变体返回的 tool_calls 数量
- 是否成功触发并行调用
- 并行成功率统计
- 最有效的提示词变体列表

## 💡 如何使用结果

1. 查看哪些提示词能触发并行 tool_calls
2. 将有效的提示词模式应用到 MaxAgent 的 prompt 中
3. 对比不同变体的表现，优化指令设计

## 🔧 自定义测试

编辑 `PROMPT_VARIANTS` 字典添加你自己的提示词：

```python
PROMPT_VARIANTS = {
    "my_test": """你的自定义提示词...""",
}
```

## 示例输出

```
变体名称                  调用数      并行
------------------------------------------------------------
baseline                  1          ❌
explicit_parallel         3          ✅
efficiency_warning        1          ❌
code_example              3          ✅
batch_edit_test           1          ❌
strong_command            3          ✅
numbered_list             1          ❌

✅ 能够触发并行 tool_calls 的提示词变体:
  - explicit_parallel (返回 3 个调用)
  - code_example (返回 3 个调用)
  - strong_command (返回 3 个调用)

并行成功率: 42.9%
```

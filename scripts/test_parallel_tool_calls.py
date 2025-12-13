#!/usr/bin/env python3
"""
测试 glm-4.6 在不同提示词下返回多个 tool_calls 的能力

用法:
    python scripts/test_parallel_tool_calls.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# 从 .env 加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from maxagent.llm.client import LLMClient, LLMConfig
from maxagent.llm.models import Message


# ============================================================================
# 测试用的工具定义
# ============================================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "编辑文件，支持单个编辑或批量编辑",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要编辑的文件路径"
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要替换的旧字符串"
                    },
                    "new_string": {
                        "type": "string",
                        "description": "替换后的新字符串"
                    },
                    "edits": {
                        "type": "array",
                        "description": "批量编辑数组",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {"type": "string"},
                                "new_string": {"type": "string"}
                            },
                            "required": ["old_string", "new_string"]
                        }
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容"
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "是否覆盖已存在的文件"
                    }
                },
                "required": ["path", "content"]
            }
        }
    }
]


# ============================================================================
# 测试提示词变体
# ============================================================================

PROMPT_VARIANTS = {
    "baseline": """请执行以下任务：
1. 读取 game.py 文件
2. 读取 config.py 文件
3. 读取 utils.py 文件

请立即执行这些操作。""",

    "explicit_parallel": """请执行以下任务：
1. 读取 game.py 文件
2. 读取 config.py 文件  
3. 读取 utils.py 文件

重要：请在一个响应中同时调用所有三个 read_file 工具，不要分多次请求。""",

    "efficiency_warning": """⚠️ 效率规则：为了减少请求次数，当需要多个独立的工具操作时，必须在同一个响应中包含所有工具调用。

任务：
1. 读取 game.py 文件
2. 读取 config.py 文件
3. 读取 utils.py 文件

请在一个响应中完成所有文件读取。""",

    "code_example": """任务：读取三个文件：game.py, config.py, utils.py

示例：正确的做法是在一个响应中调用多个工具：
```
tool_calls: [
  {"name": "read_file", "arguments": {"path": "game.py"}},
  {"name": "read_file", "arguments": {"path": "config.py"}},
  {"name": "read_file", "arguments": {"path": "utils.py"}}
]
```

请按照上述方式执行。""",

    "batch_edit_test": """请对 game.py 文件进行以下修改：
1. 将 SPEED = 5 改为 SPEED = 10
2. 将 MAX_PLAYERS = 2 改为 MAX_PLAYERS = 4
3. 将 DEBUG = False 改为 DEBUG = True

重要：使用 edit 工具的 edits 参数来批量执行这些修改。""",

    "strong_command": """🚨 必须遵守的规则：
- 当有多个独立的工具操作时，必须在一个响应中返回所有 tool_calls
- 禁止为同一组任务发送多个请求

现在请读取以下三个文件：game.py, config.py, utils.py

你必须在一个响应中调用所有三个 read_file。""",

    "numbered_list": """请按以下步骤操作：

步骤1: 读取 game.py
步骤2: 读取 config.py  
步骤3: 读取 utils.py

这些是独立的操作，可以并行执行。请在一个响应中完成所有步骤。""",
}


# ============================================================================
# 测试函数
# ============================================================================

async def test_prompt_variant(
    variant_name: str,
    user_message: str,
    llm_client: Any,
    verbose: bool = False
) -> dict:
    """测试单个提示词变体"""
    
    messages = [
        Message(
            role="system",
            content="You are a helpful assistant. You have access to tools to read and edit files."
        ),
        Message(
            role="user", 
            content=user_message
        )
    ]
    
    try:
        response = await llm_client.chat(
            messages=messages,
            tools=TOOLS,
            parallel_tool_calls=True
        )
        
        if verbose:
            print(f"\n原始响应类型: {type(response)}")
        
        # ChatResponse 的属性直接在顶层
        tool_calls = []
        finish_reason = response.finish_reason if response else None
        content = response.content if response else None
        
        if response and response.tool_calls:
            for tc in response.tool_calls:
                tool_calls.append({
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
        
        result = {
            "variant": variant_name,
            "tool_calls_count": len(tool_calls),
            "tool_calls": tool_calls,
            "success": True,
            "parallel": len(tool_calls) > 1,
            "finish_reason": finish_reason,
            "content_preview": content[:200] if content else None
        }
        
        if verbose:
            print(f"\n{'='*60}")
            print(f"变体: {variant_name}")
            print(f"finish_reason: {finish_reason}")
            if content:
                print(f"回复内容: {content[:200]}...")
            print(f"返回的 tool_calls 数量: {len(tool_calls)}")
            if tool_calls:
                print(f"Tool calls:")
                for i, tc in enumerate(tool_calls, 1):
                    print(f"  {i}. {tc['name']}({json.dumps(tc['arguments'], ensure_ascii=False)})")
            print(f"是否并行: {'✅ 是' if len(tool_calls) > 1 else '❌ 否'}")
        
        return result
        
    except Exception as e:
        print(f"\n❌ 测试 {variant_name} 失败: {e}")
        return {
            "variant": variant_name,
            "tool_calls_count": 0,
            "tool_calls": [],
            "success": False,
            "error": str(e),
            "parallel": False
        }


async def run_all_tests(verbose: bool = True):
    """运行所有测试"""
    
    # 获取 API key
    api_key = os.environ.get("GLM_API_KEY") or os.environ.get("ZHIPU_KEY")
    if not api_key:
        # 尝试从配置文件加载
        from maxagent.config.loader import load_config
        try:
            config_obj = load_config()
            # 从环境变量优先级链中获取
            if config_obj.model.default.startswith("glm"):
                api_key = os.environ.get("GLM_API_KEY") or os.environ.get("ZHIPU_KEY")
        except Exception:
            pass
    
    if not api_key:
        print("❌ 错误: 需要设置 GLM_API_KEY 或 ZHIPU_KEY 环境变量")
        print("   或者运行 llc 命令会自动从配置加载")
        return []
    
    # 创建 LLM 客户端
    config = LLMConfig(
        model="glm-4.6",
        api_key=api_key,
        parallel_tool_calls=True
    )
    
    llm_client = LLMClient(config)
    
    print(f"\n{'='*70}")
    print(f"测试 glm-4.6 模型的并行 tool_calls 能力")
    print(f"{'='*70}")
    print(f"\n模型: {config.model}")
    print(f"Base URL: {config.base_url}")
    print(f"parallel_tool_calls 配置: {config.parallel_tool_calls}")
    print(f"\n总共 {len(PROMPT_VARIANTS)} 个测试变体\n")
    
    results = []
    
    for i, (variant_name, prompt) in enumerate(PROMPT_VARIANTS.items(), 1):
        print(f"\n[{i}/{len(PROMPT_VARIANTS)}] 测试变体: {variant_name}")
        print("-" * 60)
        
        if verbose:
            print(f"提示词:\n{prompt}\n")
        
        result = await test_prompt_variant(
            variant_name, 
            prompt, 
            llm_client,
            verbose=verbose
        )
        results.append(result)
        
        # 避免请求过快
        await asyncio.sleep(1)
    
    # 汇总结果
    print(f"\n{'='*70}")
    print("测试结果汇总")
    print(f"{'='*70}\n")
    
    successful_tests = [r for r in results if r["success"]]
    parallel_tests = [r for r in results if r.get("parallel", False)]
    
    print(f"成功的测试: {len(successful_tests)}/{len(results)}")
    print(f"返回多个 tool_calls 的测试: {len(parallel_tests)}/{len(successful_tests)}")
    if successful_tests:
        print(f"并行成功率: {len(parallel_tests)/len(successful_tests)*100:.1f}%\n")
    else:
        print(f"并行成功率: N/A (没有成功的测试)\n")
    
    print("详细结果:")
    print(f"{'变体名称':<25} {'调用数':<10} {'并行':<10}")
    print("-" * 60)
    
    for result in results:
        if result["success"]:
            parallel_mark = "✅" if result["parallel"] else "❌"
            print(f"{result['variant']:<25} {result['tool_calls_count']:<10} {parallel_mark:<10}")
    
    # 找出最佳提示词
    if parallel_tests:
        print(f"\n✅ 能够触发并行 tool_calls 的提示词变体:")
        for result in parallel_tests:
            print(f"  - {result['variant']} (返回 {result['tool_calls_count']} 个调用)")
    else:
        print(f"\n❌ 没有任何提示词变体能够触发并行 tool_calls")
        print(f"   这表明 glm-4.6 模型可能不支持或不擅长并行工具调用")
    
    return results


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 glm-4.6 并行 tool_calls 能力")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细输出")
    parser.add_argument("-o", "--output", help="保存结果到 JSON 文件")
    parser.add_argument("--api-key", help="GLM API Key (或使用环境变量 GLM_API_KEY)")
    parser.add_argument("--demo", action="store_true", help="演示模式：显示提示词但不实际调用 API")
    
    args = parser.parse_args()
    
    # 演示模式：只显示提示词
    if args.demo:
        print(f"\n{'='*70}")
        print(f"演示模式：查看所有测试提示词")
        print(f"{'='*70}\n")
        
        for i, (variant_name, prompt) in enumerate(PROMPT_VARIANTS.items(), 1):
            print(f"\n[{i}/{len(PROMPT_VARIANTS)}] 变体: {variant_name}")
            print("-" * 60)
            print(prompt)
            print()
        
        print(f"\n{'='*70}")
        print("提示：使用 --api-key 参数运行实际测试")
        print(f"{'='*70}\n")
        return
    
    # 设置 API key
    if args.api_key:
        os.environ["GLM_API_KEY"] = args.api_key
    
    results = await run_all_tests(verbose=args.verbose)
    
    if not results:
        print("\n提示：使用 --demo 参数查看所有测试提示词")
        print("      使用 --api-key 参数提供 GLM API key")
        sys.exit(1)
    
    # 保存结果
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())

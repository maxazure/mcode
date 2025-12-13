#!/usr/bin/env python3
"""
测试批量编辑是否正常工作
验证简化后的 TOOL_USAGE_POLICY 是否能引导模型使用 batched edits
"""

import asyncio
import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()


# 创建测试文件
TEST_FILE_CONTENT = '''"""Simple calculator module"""

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    return a / b

def power(a, b):
    return a ** b
'''


def run_batch_edit_test():
    """运行批量编辑测试"""
    
    # 创建临时测试目录
    test_dir = tempfile.mkdtemp(prefix="maxagent_batch_test_")
    test_file = os.path.join(test_dir, "calculator.py")
    
    try:
        # 写入测试文件
        with open(test_file, 'w') as f:
            f.write(TEST_FILE_CONTENT)
        
        print(f"📁 测试目录: {test_dir}")
        print(f"📄 测试文件: {test_file}")
        print("="*60)
        
        # 构造任务 - 要求对同一文件做多处修改
        task = f"""请为 {test_file} 文件中的每个函数添加详细的 docstring，说明函数的功能、参数和返回值。

要求：
1. 每个函数都需要添加 docstring
2. docstring 应该包含函数描述、Args、Returns 三部分
3. 使用 Google 风格的 docstring 格式

请先读取文件，然后使用批量编辑一次性完成所有修改。
"""
        
        print(f"📝 任务: {task[:100]}...")
        print("="*60)
        
        # 设置 debug 日志
        env = os.environ.copy()
        env["MAXAGENT_DEBUG_LOG"] = "1"  # 启用 debug 日志
        
        # 运行 mcode 命令
        print("\n🚀 运行 mcode edit 命令...")
        result = subprocess.run(
            ["python", "-m", "maxagent", "edit", test_file, task],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=180,  # 3 分钟超时
            env=env
        )
        
        print("\n📤 STDOUT:")
        print(result.stdout[:2000] if len(result.stdout) > 2000 else result.stdout)
        
        if result.stderr:
            print("\n📤 STDERR:")
            print(result.stderr[:1000] if len(result.stderr) > 1000 else result.stderr)
        
        # 验证文件是否被正确修改
        with open(test_file, 'r') as f:
            updated_content = f.read()
        
        print("\n" + "="*60)
        print("📄 修改后的文件内容:")
        print(updated_content)
        
        docstring_count = updated_content.count('Args:')
        print(f"\n📊 包含 {docstring_count} 个 'Args:' 标记")
        
        return result.returncode == 0
            
    finally:
        # 清理临时目录
        shutil.rmtree(test_dir, ignore_errors=True)
        print(f"\n🗑️ 已清理临时目录: {test_dir}")


if __name__ == "__main__":
    result = run_batch_edit_test()
    sys.exit(0 if result else 1)

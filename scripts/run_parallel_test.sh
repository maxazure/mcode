#!/bin/bash
# 从 MaxAgent 配置加载 API key 并运行 parallel tool calls 测试

set -e

cd "$(dirname "$0")/.."

# 激活虚拟环境
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# 尝试从配置加载 API key
if [ -z "$GLM_API_KEY" ] && [ -z "$ZHIPU_KEY" ]; then
    # 从 llc 运行时环境获取
    export GLM_API_KEY=$(python -c "
import os
import sys
sys.path.insert(0, 'src')
from maxagent.config.loader import load_config
try:
    config = load_config()
    # 简单起见，假设用户已配置 GLM key
    key = os.environ.get('GLM_API_KEY') or os.environ.get('ZHIPU_KEY')
    if key:
        print(key)
except:
    pass
" 2>/dev/null)
fi

# 运行测试
python scripts/test_parallel_tool_calls.py "$@"

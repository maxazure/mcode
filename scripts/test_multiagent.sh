#!/usr/bin/env bash
# 多 Agent 协作测试脚本
# 用于测试 subagent 调用自定义 agent profile 的场景
#
# 使用方法:
#   ./scripts/test_multiagent.sh [场景名称]
#
# 可用场景:
#   simple   - 简单测试 (默认)
#   website  - 企业网站创建测试
#   analyze  - 代码分析测试

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCENARIO="${1:-simple}"

echo -e "${GREEN}=== 多 Agent 协作测试 ===${NC}"
echo -e "${BLUE}场景: ${SCENARIO}${NC}"
echo ""

# 检查 agent profiles 目录
AGENTS_DIR="$HOME/.llc/agents"
if [ ! -d "$AGENTS_DIR" ]; then
    echo -e "${YELLOW}创建 agents 目录: $AGENTS_DIR${NC}"
    mkdir -p "$AGENTS_DIR"
fi

# 列出已有的 agent profiles
echo -e "${GREEN}当前已配置的 Agent Profiles:${NC}"
ls -la "$AGENTS_DIR"/*.md 2>/dev/null || echo "  (暂无配置文件)"
echo ""

# 设置调试日志
export MAXAGENT_DEBUG_LOG="/tmp/multiagent_$(date +%Y%m%d_%H%M%S).log"
echo -e "${YELLOW}调试日志: $MAXAGENT_DEBUG_LOG${NC}"
echo ""

# 根据场景选择测试提示词
case "$SCENARIO" in
    "simple")
        # 简单测试：验证 subagent 基本功能
        OUTPUT_DIR="demo/multiagent_test"
        mkdir -p "$OUTPUT_DIR"
        
        PROMPT='这是一个多 Agent 协作的简单测试。请按以下步骤完成：

1. 首先，调用 subagent 工具（agent_type="general"）来生成一个简短的 Python 程序。
   任务描述：创建一个简单的 Python 程序，实现一个计算器函数，支持加减乘除。
   将结果保存到 demo/multiagent_test/calculator.py

2. 然后，调用另一个 subagent 工具（agent_type="general"）来生成这个程序的测试文件。
   任务描述：为 calculator.py 创建单元测试文件。
   将结果保存到 demo/multiagent_test/test_calculator.py

3. 最后，总结完成的工作。

请确保每个任务都使用独立的 subagent 调用来完成。'

        VERIFY_FILES=("$OUTPUT_DIR/calculator.py" "$OUTPUT_DIR/test_calculator.py")
        ;;
        
    "website")
        # 网站创建测试
        OUTPUT_DIR="demo/enterprise_website"
        mkdir -p "$OUTPUT_DIR"
        
        PROMPT='请为一家名为"云智科技"的人工智能公司创建一个简单的企业官网首页。

公司信息：
- 行业：人工智能/机器学习
- 核心业务：AI 解决方案、数据分析、智能客服
- 目标客户：中大型企业
- 网站风格：专业、科技感、简洁

请按以下步骤完成：

1. 调用 subagent(agent_type="general", task="作为网站内容策划师，为云智科技生成网站首页的文案内容，包括：公司口号、核心服务介绍（3项）、特色优势（4项）、联系方式。以 YAML 格式输出。")

2. 调用 subagent(agent_type="general", task="作为网站前端工程师，创建一个完整的 HTML 页面，包含导航栏、Hero 区域、服务介绍、特色优势、联系方式。保存到 demo/enterprise_website/index.html")

3. 调用 subagent(agent_type="general", task="作为 CSS 设计师，为企业网站创建专业的样式文件，使用蓝色科技风格，响应式设计。保存到 demo/enterprise_website/style.css")

请确保每个 subagent 都实际执行并输出结果，最后汇总完成的工作。'

        VERIFY_FILES=("$OUTPUT_DIR/index.html" "$OUTPUT_DIR/style.css")
        ;;
        
    "analyze")
        # 代码分析测试
        OUTPUT_DIR="demo/code_analysis"
        mkdir -p "$OUTPUT_DIR"
        
        PROMPT='请对当前项目的核心代码进行分析。

请按以下步骤完成：

1. 调用 subagent(agent_type="explore", root="src/maxagent/core", task="探索 core 目录的代码结构，找出主要的类和函数")

2. 调用 subagent(agent_type="general", task="根据上一步的探索结果，编写一份简短的代码架构文档，保存到 demo/code_analysis/architecture.md")

请确保每个 subagent 都实际执行并输出结果。'

        VERIFY_FILES=("$OUTPUT_DIR/architecture.md")
        ;;
        
    *)
        echo -e "${RED}未知场景: $SCENARIO${NC}"
        echo "可用场景: simple, website, analyze"
        exit 1
        ;;
esac

echo -e "${GREEN}开始测试...${NC}"
echo "提示词:"
echo "---"
echo "$PROMPT" | head -25
if [ $(echo "$PROMPT" | wc -l) -gt 25 ]; then
    echo "..."
fi
echo "---"
echo ""

# 执行测试
echo -e "${YELLOW}执行 llc chat ...${NC}"
llc chat "$PROMPT"

# 检查输出
echo ""
echo -e "${GREEN}=== 测试结果 ===${NC}"
ALL_PASSED=true
for FILE in "${VERIFY_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        echo -e "${GREEN}✅ $(basename $FILE) 已创建${NC}"
        echo "   文件大小: $(wc -c < "$FILE") bytes"
    else
        echo -e "${RED}❌ $(basename $FILE) 未创建${NC}"
        ALL_PASSED=false
    fi
done

echo ""
if [ "$ALL_PASSED" = true ]; then
    echo -e "${GREEN}✅ 所有验证文件已创建！${NC}"
else
    echo -e "${RED}❌ 部分文件未创建，请检查日志${NC}"
fi

echo ""
echo -e "${YELLOW}调试日志位置: $MAXAGENT_DEBUG_LOG${NC}"
echo "查看日志: tail -100 $MAXAGENT_DEBUG_LOG"

# 显示测试统计
if [ -f "$MAXAGENT_DEBUG_LOG" ]; then
    echo ""
    echo -e "${BLUE}=== 日志统计 ===${NC}"
    echo "Session 数量: $(grep -c 'Session started' "$MAXAGENT_DEBUG_LOG" 2>/dev/null || echo 0)"
    echo "工具调用数量: $(grep -c '"tool_calls_count"' "$MAXAGENT_DEBUG_LOG" 2>/dev/null || echo 0)"
    echo "subagent 调用: $(grep -c '"name": "subagent"' "$MAXAGENT_DEBUG_LOG" 2>/dev/null || echo 0)"
fi

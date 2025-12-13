# 多 Agent 协作测试提示词

## 提示词 1: 企业网站开发（推荐）

```
请为一家名为"云智科技"的人工智能公司创建企业官网首页。

公司信息：
- 行业：人工智能/机器学习  
- 核心业务：AI 解决方案、数据分析、智能客服
- 目标客户：中大型企业
- 网站风格：专业、科技感、简洁现代

请按以下步骤使用 subagent 工具协作完成：

步骤 1：调用 subagent(agent_type="general", task="作为网站内容策划师，为云智科技生成网站首页文案。包括：公司主口号（10-15字）、副标题（20-30字）、三个核心服务介绍（每个50字左右）、三个企业优势（每个30字）、联系方式。输出为结构化格式。")

步骤 2：调用 subagent(agent_type="general", task="作为前端工程师，使用步骤1的文案内容，创建完整的企业网站首页 HTML 文件。要求：语义化 HTML5、响应式布局、包含 header/hero/services/features/contact/footer 区块。使用 write_file 保存到 demo/enterprise_website/index.html")

步骤 3：调用 subagent(agent_type="general", task="作为 CSS 设计师，为企业网站创建专业样式。配色方案：主色蓝色 #2563eb、背景浅灰 #f8fafc、文字深灰 #1e293b。包含：CSS 变量、Flexbox/Grid 布局、响应式断点、悬停动画效果。使用 write_file 保存到 demo/enterprise_website/style.css")

请确保每个 subagent 都实际执行并输出结果，最后汇总创建的文件列表。
```

## 提示词 2: 简化版本

```
请创建一个简单的企业网站，使用 subagent 工具：

1. 调用 subagent(agent_type="general", task="作为内容策划师，生成科技公司网站文案")
2. 调用 subagent(agent_type="general", task="作为前端工程师，创建 HTML 页面，保存到 demo/test_website/index.html")
3. 调用 subagent(agent_type="general", task="作为设计师，创建 CSS 样式，保存到 demo/test_website/style.css")
```

## 提示词 3: 使用内置 agent 类型

```
请分析并创建一个简单网站：

1. 调用 subagent(agent_type="architect", task="分析创建企业网站首页需要的文件结构和技术方案")
2. 调用 subagent(agent_type="coder", task="创建 demo/simple_site/index.html，包含完整的企业首页 HTML")
3. 调用 subagent(agent_type="coder", task="创建 demo/simple_site/style.css，包含基础样式")
```

## 提示词 4: 并行测试

```
请同时准备三个网站模块的内容，使用 3 个并行的 subagent：

1. subagent(agent_type="general", task="生成首页 Hero 区域的文案内容")
2. subagent(agent_type="general", task="生成服务介绍区域的文案内容")  
3. subagent(agent_type="general", task="生成关于我们区域的文案内容")

请并行调用这三个 subagent。
```

## 测试命令

```bash
# 基础测试
mcode chat "上述提示词内容"

# 带 trace 调试
mcode chat --trace "上述提示词内容"

# 带完整日志
MAXAGENT_DEBUG_LOG=/tmp/test.log mcode chat --trace "上述提示词内容"
```

## 验证结果

```bash
# 检查生成的文件
ls -la demo/enterprise_website/
cat demo/enterprise_website/index.html

# 在浏览器中预览
open demo/enterprise_website/index.html
# 或启动简单服务器
cd demo/enterprise_website && python -m http.server 8080
```

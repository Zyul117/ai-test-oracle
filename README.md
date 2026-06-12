# 🔮 AI Test Oracle — 智能接口测试预言机

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 💡 一句话介绍

解决软件测试中的 **Oracle Problem**（预言机问题）—— 用 LLM 自动判断 API 返回结果是否正确，无需人工编写断言。

## 🤔 什么是 Oracle Problem？

测试中最难的问题之一：你发出了一个 HTTP 请求，拿到了一个 JSON 响应——**但你怎么知道这个响应是"正确的"？**

传统方案是人工写断言（assert），但断言只能检查你能想到的问题。如果接口返回了 `balance: -500`，断言 `status_code == 200` 会通过，但负数余额本身就是一个 Bug——**这种"隐性 Bug"传统断言很难捕捉**。

本项目用 LLM 充当"测试预言机"，像一位有经验的测试工程师一样审查每个响应。

## 🏗️ 架构设计

```
用户输入 API 描述
       │
       ▼
┌──────────────────────┐
│  输入生成器           │  基于边界值、等价类等方法生成测试参数
│  (InputGenerator)    │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│  请求执行器           │  发送 HTTP 请求，收集响应
│  (RequestRunner)     │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│          分层判断引擎 (LayeredComparator)  │
│                                          │
│  Layer 1: Schema 校验 (jsonschema)       │  ← 零成本、零幻觉
│  Layer 2: LLM Oracle 语义判断 (CoT)      │  ← 发现隐性 Bug
└──────────────┬───────────────────────────┘
               │
               ▼
┌──────────────────────┐
│  测试报告             │
│  (ReportGenerator)   │
└──────────────────────┘
```

### 两层判断策略

| 层级 | 技术 | 成本 | 准确率 | 检测内容 |
|------|------|------|--------|---------|
| Layer 1 | jsonschema 库 | 零 | 100% | 字段类型、结构、必填项 |
| Layer 2 | LLM + Chain-of-Thought | ~1K tokens/次 | 取决于模型 | 业务逻辑、数据合理性 |

### Chain-of-Thought 推理

LLM Oracle 的 System Prompt 强制 AI 按三步推理：

1. **Step 1 — 数据结构检查**：字段类型、缺失项、范围合理性
2. **Step 2 — 业务逻辑检查**：业务规则是否被违反、字段间是否自洽
3. **Step 3 — 综合判断**：pass / fail / uncertain + 置信度评分

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 LLM

```bash
# 使用 OpenAI
export OPENAI_API_KEY="sk-your-api-key"
export LLM_MODEL="gpt-4o-mini"

# 或使用 DeepSeek（更便宜，推荐）
export OPENAI_API_KEY="sk-your-deepseek-key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"

# 或使用通义千问
export OPENAI_API_KEY="sk-your-qwen-key"
export OPENAI_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export LLM_MODEL="qwen-plus"
```

### 3. 运行

```bash
# Web 界面
streamlit run app.py

# 或命令行快速验证
python demo.py
```

### 4. 使用

1. 在侧边栏配置目标 API 地址
2. 在 Tab 1 输入接口描述 + 参数定义
3. 点击「生成测试用例」
4. 切到 Tab 2，点击「执行测试 & AI 判断」
5. 在 Tab 3 查看 Oracle 判断报告

## 📁 项目结构

```
ai-test-oracle/
├── app.py                  # Streamlit Web 界面
├── demo.py                 # 命令行快速演示
├── src/
│   ├── __init__.py
│   ├── llm_client.py       # LLM API 调用封装
│   ├── llm_oracle.py       # 🔑 LLM Oracle 核心（Chain of Thought）
│   ├── schema_validator.py # Layer 1: Schema 结构校验
│   ├── input_generator.py  # 测试输入生成（边界值/等价类）
│   ├── request_runner.py   # HTTP 请求执行器
│   ├── comparator.py       # 分层判断引擎
│   └── report.py           # 报告生成器
├── prompts/
│   └── oracle_system.txt   # Oracle System Prompt（核心）
├── examples/               # 示例输入输出
├── requirements.txt
└── README.md
```

## 🎯 关键设计决策

### 为什么不是"调 LLM 生成测试用例"？

市面上很多项目是"输入 API 描述 → LLM 生成测试用例 → 执行"。这个模式有两个问题：

1. **生成质量无法保证**：LLM 生成的用例可能遗漏关键场景
2. **没有触及测试核心痛点**：测试最难的不是"生成输入"，而是"判断输出"

本项目换了一个角度：**输入的生成用经典的测试方法（边界值、等价类），输出判断用 LLM**——这才是 AI 真正有优势的地方。

### 为什么是两层架构而非纯 LLM？

- **Layer 1 (Schema) 零成本**：不需要调用 LLM，响应快，100% 准确
- **Layer 2 (LLM) 处理复杂场景**：只在 Schema 通过后才调用，节省成本
- **分层隔离**：每一层的结果可独立审查，不会混在一起

### 减少 LLM 幻觉的策略

- **Chain-of-Thought**：强制推理过程，而非直接猜答案
- **Uncertain 选项**：不像二元分类器那样强制 pass/fail，不确定就说不确定
- **低 Temperature**：测试场景需要确定性，使用 0.1-0.3

## 📊 示例输出

```
==================================================
       AI Test Oracle — 测试报告
==================================================
总测试数: 12
✅ 通过: 8
❌ 失败: 3
❓ 不确定: 1
通过率: 66.7%

疑似 Bug 详情:
[1] 边界值 userId = 0
    来源: Layer 2 — LLM 语义判断
    详情: 返回空数组，但未明确告知用户不存在。不确定是合法行为还是bug。
[2] 异常值 page = -1
    来源: Layer 1 — Schema 校验
    详情: 返回了全部数据而非报错，缺少参数校验
==================================================
```

## 🌟 面试亮点（技术方向）

如果你的简历上有这个项目，面试可以聊这些：

1. **Oracle Problem 是测试领域公认的难题**（1978年由 Weyuker 提出），你针对它做了一个实际的解决方案
2. **分层架构设计**：零成本的结构校验 + LLM 语义判断，体现了工程权衡思维
3. **CoT Prompt Engineering**：不是简单地问 LLM "对不对"，而是设计了强制推理流程
4. **置信度机制**：不是二元判断，而是引入了 uncertain 状态和置信度分数
5. **对 AI 局限性的认知**：能清楚说明 LLM 幻觉问题以及你的缓解策略

## 🙋 FAQ

**Q: LLM 判断错了怎么办？**
A: 这就是为什么有 uncertain 状态和置信度。低置信度的结果标记出来让人工复审。Oracle 是辅助工具，不是替代品。

**Q: 适合哪些 API？**
A: RESTful API、返回 JSON 的接口最佳。GraphQL、gRPC 需要额外适配。

**Q: API 费用高吗？**
A: gpt-4o-mini 约 $0.15/1M input tokens，一次 Oracle 判断约消耗 500-1000 tokens，约 $0.0001-0.0002。用 DeepSeek 更便宜。

## 📄 License

MIT

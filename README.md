# AI Test Oracle - 智能接口测试预言机

## 项目介绍

用大模型自动判断 API 返回结果对不对，不用人工写断言。

## 为什么要做

基于针对 Oracle Problem——测试里最大的难点不是"生成测试数据"，是"判断结果对不对"。

举个例子：一个接口返回了 `balance: -500`，断言 `status_code == 200` 是通过的，但余额为负显然是个 Bug。传统断言只能检查你提前想到的问题，这种隐性 Bug 很难被发现。

所以我开始去试着用 LLM 当"审查员"，让 AI 来判断响应是不是真的正确。

## 怎么实现的

整体流程：

```
输入接口描述 → 生成测试参数 → 发送请求 → 两层判断 → 出报告
```

### 判断分两层

**第一层 — Schema 结构校验（不用 AI）**

用 Python 的 jsonschema 库直接检查字段类型、有没有缺必填字段。这层不用调 AI，零成本，100% 准确。

**第二层 — LLM 语义判断**

Schema 通过后，再交给 AI 看业务逻辑合不合理。在 Prompt 里让 AI 按三步推理：
1. 先检查数据结构
2. 再分析业务逻辑
3. 最后下结论

这样做是因为试过直接问"这个响应对不对"，AI 经常乱说。让它一步步推理后效果好了很多。

如果 AI 拿不准，就标成"不确定"，不会强行给结论。

## 快速开始

```bash
# 1. 装依赖
pip install -r requirements.txt

# 2. 配置 API Key（以 DeepSeek 为例，便宜）
export OPENAI_API_KEY="sk-你的key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"

# 3. 命令行快速体验
python demo.py

# 4. 或者启动 Web 界面
streamlit run app.py
```

打开浏览器访问 `http://localhost:8501`，按界面提示操作就行。

## 项目结构

```
├── app.py                  # Streamlit 界面
├── demo.py                 # 命令行演示
├── src/
│   ├── llm_client.py       # LLM 调用封装
│   ├── llm_oracle.py       # Oracle 核心逻辑
│   ├── schema_validator.py # Schema 结构校验
│   ├── input_generator.py  # 测试输入生成
│   ├── request_runner.py   # 发 HTTP 请求
│   ├── comparator.py       # 两层判断组合
│   └── report.py           # 报告生成
├── prompts/
│   └── oracle_system.txt   # Oracle 的 System Prompt
└── requirements.txt
```

## 局限和想改进的地方

- LLM 偶尔还是会误判，准确率不是 100%，更像是一个辅助工具
- 目前只支持 REST API，返回 JSON 的场景
- 每个用例都要调一次 AI，批量跑成本不低
- 如果以后有机会，想试试集成到 CI/CD 流程里

## 技术栈

Python / Streamlit / OpenAI API / jsonschema / requests


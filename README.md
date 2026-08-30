# AI Test Oracle — 分层 API 测试预言机

用大模型判断 API 返回结果对不对，不用把每条断言都手写出来。

提供两种用法，共用同一套判定核心：

- **pytest 插件** — `pip install -e .` 后即可用 `ai_assert` fixture，用自然语言写期望
- **Web 应用** — Streamlit 界面，走完整流程（发请求 → 分层判定 → 出报告）

## 要解决什么问题

接口自动化里最难的不是「造测试数据」，是「判断结果对不对」—— 即测试预言机问题（Oracle Problem）。

传统断言只能验证你**提前想到**的规则。比如一个接口返回：

```json
{ "order_id": 1002, "items": [{ "price": 50.0, "qty": 3 }], "total": 100.0 }
```

`assert status_code == 200` 通过，字段类型也全对，JSON Schema 校验也过 —— 但 `total` 应该是 150。这种**结构合法、语义错误**的缺陷，传统断言基本覆盖不到。

## 怎么做的

```
输入接口描述 → 发送请求 → 两层判定 → 出报告
```

### Layer 1 — Schema 结构校验（不调 AI）

用 `jsonschema` 校验字段类型、必填项，外加一组通用检查（null 值、负数金额、空集合）。

零成本、零幻觉、结果 100% 可复现。

### Layer 2 — LLM 语义判断

Layer 1 通过后才调 LLM —— 结构性问题不需要大模型参与，挡在第一层能省掉 token。

Prompt 里强制模型按 Chain-of-Thought 三步推理：

1. 先检查数据结构
2. 再分析业务逻辑与字段间自洽性
3. 最后下结论并给置信度

直接问「这个响应对不对」模型经常乱说，改成分步推理后判定质量明显更稳。

### 三态结果

| 结果 | 含义 |
|---|---|
| `pass` | 符合预期 |
| `fail` | 存在疑似缺陷 |
| `uncertain` | 信息不足或期望描述模糊，**不硬给结论** |

`uncertain` 是刻意设计的：测试工具误报的代价很高，宁可交人工复核，也不要假阳性。

## 快速开始

```bash
pip install -e ".[web,dev]"

# 配置 LLM（以 DeepSeek 为例，便宜）
export OPENAI_API_KEY="sk-你的key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"
```

### 用法一：pytest 插件

```python
def test_user_balance(ai_assert):
    resp = requests.get("http://127.0.0.1:8000/api/user/2")

    assert resp.status_code == 200          # 传统断言：过
    assert ai_assert(resp.json(), "余额不应为负数")   # 语义断言：抓到了
```

`ai_assert` 返回 `Verdict` 对象，只有 `pass` 为真值，所以可以直接 `assert`。需要区分 `uncertain` 时读 `.verdict` / `.confidence` / `.reason`。

```bash
# 起本地 mock API
python mock_server.py

# 端到端演示（最直观的一屏）
python demo.py

# 跑测试
pytest -v
```

### 用法二：Web 界面

```bash
streamlit run app.py     # http://localhost:8501
```

## 项目结构

```
ai_oracle/
├── verdict.py      三态判定契约（统一 pass/fail/uncertain + 字段容错）
├── llm.py          LLM 调用 + 三级 JSON 降级解析
├── oracle.py       语义判定（CoT 完整模式 / 轻量断言模式）
├── layers.py       Layer 1 结构校验 + 两层组合
├── runner.py       HTTP 请求执行
├── report.py       报告汇总
├── plugin.py       pytest 插件（ai_assert fixture）
└── prompts/        system prompt（文件化管理，便于调整与对比）

app.py              Streamlit 界面
demo.py             端到端演示（发请求 → 分层判定 → 出报告）
mock_server.py      本地 mock API（内置若干「状态码 200 但数据有问题」的接口）
benchmark/          准确率基准集（见 benchmark/README.md）
tests/              分层测试
```

## 准确率基准集

光说「LLM 判得准」是主观的，所以做了一套**人工标注了正确答案**的用例集，
每次改 prompt 后跑一遍，就能知道是变好还是变差。

```bash
python mock_server.py                                              # 另开一个窗口
python benchmark/run_benchmark.py --cases benchmark/cases.example.yaml
```

统计把**漏报**（该报 fail 却判 pass）和**误报**（该判 pass 却报 fail）分开看 ——
两者代价不同，漏报会让缺陷进生产，误报只是浪费时间。

用例分两类：能从响应字面直接读出结论的**易判样本**，以及需要算术自洽、
跟字段关系推理、或者干脆就信息不足的**难判样本**。后者里有一类正确答案是
`uncertain` —— 用来验证模型不会硬给结论，这是三态设计的核心价值。

> 完整用例集由实际项目的接口用例脱敏改写而成，**不入库**（见 `.gitignore`）。
> 仓库里只有合成数据的 `cases.example.yaml` 展示格式。
> 基准结果的解释边界写在 [benchmark/README.md](benchmark/README.md)。

## 工程上处理的几个问题

**LLM 不按格式输出** — 三级降级解析：整段 `json.loads` → 提取 ` ```json ` 代码块 → 提取最外层花括号 → 兜底 `uncertain`。解析失败不抛异常，不中断整轮测试。

**判定结果契约不统一** — 早期 Web 侧字段叫 `summary`、插件侧叫 `reason`，插件里直接 `result["reason"]` 取值，模型少返一个字段就 `KeyError`。现在统一走 `Verdict.from_dict()`，两个历史字段名都兼容，缺字段、非法枚举值、置信度越界全部有兜底。

**无 API Key 时测试挂死** — OpenAI SDK 默认会反复重试，跑测试要卡几分钟。现在显式设了 `timeout` / `max_retries`，并在插件里用 `pytest_collection_modifyitems` 把标了 `live_llm` 的用例在无 Key 时自动 skip。所以 CI 不配 Key 也能跑确定性部分。

**凭据泄露** — `RequestRunner` 不把 `Authorization` 头记进结果对象，避免写进报告。

## 测试

```bash
pytest -v                      # 无 Key：确定性用例全跑，LLM 用例自动 skip
pytest -m live_llm -v -s       # 配了 Key：跑真实 LLM 判定
```

分三层：

| 文件 | 覆盖 | 需要 Key |
|---|---|---|
| `tests/test_core.py` | Verdict 契约容错、三级 JSON 解析、Layer 1 校验、报告汇总 | 否 |
| `tests/test_runner.py` | HTTP 执行、异常处理、mock 数据可判定性 | 否 |
| `tests/test_ai_assert.py` | 真实 LLM 语义判定、端到端 | 是（否则 skip） |

`test_runner.py` 里有一组用例专门验证「Layer 1 抓不到语义缺陷」—— 结构合法但 `total` 不自洽、状态机矛盾这些必须靠 Layer 2，这也是分层设计的依据。

## 局限

- LLM 判定不是 100% 准确，定位是**辅助发现**，不适合当唯一门禁
- 每条 `ai_assert` 都要调一次 API，大批量回归成本不低；目前没做结果缓存
- 只支持返回 JSON 的 REST 接口
- 期望描述写得越模糊，`uncertain` 比例越高

## 技术栈

Python · pytest（插件开发 / fixture / hook）· jsonschema · OpenAI 兼容 API · requests · Streamlit · GitHub Actions

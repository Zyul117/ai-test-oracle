# 基准集 —— 衡量语义判定准确率

给预言机一批**人工标注了正确答案**的用例，跑一遍看判得对不对。

没有这一步，「LLM 判定有效」只是主观感觉；有了它才能给出可复现的数字，
也才能在改 prompt 后知道是变好还是变坏。

## 怎么跑

```bash
# 1. 起本地 mock
python mock_server.py

# 2. 配置 LLM
export OPENAI_API_KEY="sk-..."
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
export LLM_MODEL="deepseek-chat"

# 3. 跑示例用例集（合成数据，仓库自带）
python benchmark/run_benchmark.py --cases benchmark/cases.example.yaml

# 4. 跑完整用例集（需自备 cases.yaml）
python benchmark/run_benchmark.py --out benchmark/results/run1.json
```

## 用例格式

```yaml
- id: EX-01
  module: 用户            # 模块分类
  priority: P0            # 优先级
  auth: token             # 认证方式
  title: 正常用户信息
  method: GET
  path: /api/user/1
  body: {}                # POST 请求体，可省略
  expectation: >          # 自然语言期望 —— 直接喂给 ai_assert
    响应应包含 user_id、name、email、balance 四个字段，
    且 balance 不应为负数。
  expected_verdict: pass  # 人工标注的正确答案：pass / fail / uncertain
```

`expectation` 就是 `ai_assert(响应, 期望)` 的第二个参数，
`expected_verdict` 是 ground truth，用来算准确率。

## 统计口径

| 指标 | 含义 |
|---|---|
| 准确率 | 判定与标注一致的比例 |
| **漏报** | 该报 `fail` 却判了 `pass` —— 缺陷被放过，测试工具最危险的错误 |
| **误报** | 该判 `pass` 却报了 `fail` —— 制造无效排查，消耗信任 |
| 不确定 | 判了 `uncertain`，交人工复核（不算错，但比例过高说明期望写得不够清楚） |

漏报和误报分开统计，因为两者代价完全不同：漏报会让缺陷进生产，
误报只是浪费时间。测试工具应该优先压低漏报。

## 用例集设计

用例分两类，缺一不可：

**易判样本** —— 结论能从响应字面直接读出（字段缺失、状态码不对、布尔值反了）。
这类全对是应该的，作用是确认基本能力没退化。

**难判样本** —— 需要额外推理才能发现问题：

- 算术自洽：`balance_before + amount == balance_after`
- 跨字段关系：`total > size` 时当前页 `list` 长度应等于 `size`
- 常识约束：流水时间戳不该是未来时间
- **信息不足**：期望描述模糊、或引用了响应里根本看不到的信息
  —— 这类正确答案是 `uncertain`，用来验证模型不会硬给结论

第二类里的 `uncertain` 用例特别重要。三态设计的价值就在于「拿不准时诚实说不知道」，
如果基准集里没有这类样本，等于完全没测到这个设计。

## 真实用例集的脱敏原则

完整用例集（`benchmark/cases.yaml`）由实际项目的接口测试用例改写而来，
**不入库**（见 `.gitignore`）。改写时：

- 真实域名 → `http://127.0.0.1:8000`（本地 mock）
- 真实接口路径 → 语义等价的通用路径
- 真实手机号 / 邮箱 / token → 示例值
- **安全类用例全部剔除**（限流、注入、越权、IDOR 等），不纳入基准集
- 剔除所有内部缺陷记录与修复状态

保留下来的是方法论：模块划分、优先级、认证方式，以及最关键的
**「预期结果」自然语言描述** —— 它天然就是语义断言的输入格式。

## 结果的解释边界

基准集能证明的：在这批标注用例上，判定与人工标注一致，且三态行为符合设计。

基准集**不能**证明的：

- 不代表在任意 API 上的普适准确率 —— 用例是自己设计的，存在选择偏差
- 用例作者与 prompt 作者是同一人，可能无意中写出「对这套 prompt 友好」的期望
- 样本量小（几十条），置信区间宽

要让结论更硬，可行的方向：扩大样本量、让他人独立标注、
用生产环境真实响应而非 mock 数据。

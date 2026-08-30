"""
LLM 语义断言测试 —— 需要真实 API Key

没配 OPENAI_API_KEY 时这些用例会自动 skip（插件的
pytest_collection_modifyitems 负责），所以 CI 里也能安全跑。

跑真实调用：
    set OPENAI_API_KEY=sk-xxx
    set OPENAI_BASE_URL=https://api.deepseek.com/v1
    set LLM_MODEL=deepseek-chat
    pytest tests/test_ai_assert.py -v -s
"""

import pytest

from ai_oracle import FAIL, PASS, UNCERTAIN, RequestRunner

pytestmark = pytest.mark.live_llm


class TestAIAssert:
    """ai_assert fixture 的真实判定能力"""

    def test_detects_negative_balance(self, ai_assert):
        """状态码 200、结构合法，但余额为负 —— 传统断言查不出来"""
        result = ai_assert(
            {"user_id": 2, "name": "李四", "balance": -500.0},
            "余额 balance 不应该为负数",
        )
        print(f"\n  判定: {result.verdict} ({result.confidence:.0%}) — {result.reason}")
        assert result.verdict == FAIL

    def test_accepts_normal_data(self, ai_assert):
        result = ai_assert(
            {"user_id": 1, "name": "张三", "email": "z@example.com", "balance": 1200.5},
            "用户的 name、email、balance 字段都存在且取值合理",
        )
        print(f"\n  判定: {result.verdict} ({result.confidence:.0%}) — {result.reason}")
        assert result.verdict == PASS

    def test_detects_missing_field(self, ai_assert):
        result = ai_assert(
            {"user_id": 3, "name": "王五"},
            "响应必须同时包含 user_id、name、email 三个字段",
        )
        print(f"\n  判定: {result.verdict} — {result.reason}")
        assert result.verdict == FAIL

    def test_detects_inconsistent_total(self, ai_assert):
        """结构完全合法，Layer 1 抓不到，只能靠语义判断"""
        result = ai_assert(
            {"order_id": 1002, "items": [{"price": 50.0, "qty": 3}], "total": 100.0},
            "订单 total 应该等于所有 items 的 price × qty 之和",
        )
        print(f"\n  判定: {result.verdict} — {result.reason}")
        assert result.verdict == FAIL

    def test_vague_expectation_gives_uncertain(self, ai_assert):
        """期望描述模糊时不该硬给结论"""
        result = ai_assert(
            {"status": "active", "code": 42},
            "这个响应应该符合某个我没说明的内部规范",
        )
        print(f"\n  判定: {result.verdict} — {result.reason}")
        assert result.verdict == UNCERTAIN

    def test_verdict_is_truthy_only_when_pass(self, ai_assert):
        """可以直接 assert ai_assert(...)，uncertain 不会被当通过"""
        result = ai_assert({"balance": 100.0}, "余额不为负数")
        assert bool(result) == (result.verdict == PASS)


class TestAgainstMockServer:
    """端到端：发真实 HTTP 请求 → LLM 判定"""

    def test_end_to_end_bad_data(self, ai_assert, mock_server):
        resp = RequestRunner(mock_server).run(
            {"test_name": "余额为负", "path": "/api/user/2"}
        )
        assert resp.status_code == 200           # 传统断言在这里就通过了
        result = ai_assert(resp.response_body, "余额不应为负数")
        print(f"\n  判定: {result.verdict} — {result.reason}")
        assert result.verdict == FAIL            # 预言机抓到了

    def test_end_to_end_good_data(self, ai_assert, mock_server):
        resp = RequestRunner(mock_server).run(
            {"test_name": "正常用户", "path": "/api/user/1"}
        )
        result = ai_assert(resp.response_body, "用户信息完整且余额非负")
        print(f"\n  判定: {result.verdict} — {result.reason}")
        assert result.verdict == PASS

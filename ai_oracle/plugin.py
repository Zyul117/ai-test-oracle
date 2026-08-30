"""
pytest 插件 —— 通过 fixture 把 LLM 语义断言注入测试用例

pyproject.toml 里用 entry-points.pytest11 注册，
pip install -e . 之后任何 pytest 项目都能直接用 ai_assert，不需要写 conftest。

用法：
    def test_user_api(ai_assert):
        resp = requests.get(".../user/1")
        assert ai_assert(resp.json(), "余额不能为负数，用户名和邮箱必须存在")
"""

import pytest

from .llm import has_api_key
from .verdict import Verdict


def pytest_configure(config):
    """注册自定义 marker，避免 --strict-markers 下报 unknown marker"""
    config.addinivalue_line(
        "markers", "ai_assert: 使用 LLM 语义断言的测试用例"
    )
    config.addinivalue_line(
        "markers", "live_llm: 需要真实 LLM API Key（未配置时自动 skip）"
    )


def pytest_collection_modifyitems(config, items):
    """
    没配 API Key 时自动 skip 标了 live_llm 的用例。

    合并前 pytest-ai-assert 没有这层保护：无 Key 时 OpenAI SDK 会一直重试，
    跑 tests/ 会卡好几分钟才失败。
    """
    if has_api_key():
        return

    skip = pytest.mark.skip(reason="未配置 OPENAI_API_KEY，跳过需要真实 LLM 调用的用例")
    for item in items:
        if "live_llm" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def ai_oracle():
    """session 级共享 LLMOracle，避免每条用例都重建客户端"""
    from .oracle import LLMOracle
    return LLMOracle()


@pytest.fixture
def ai_assert(ai_oracle, request):
    """
    LLM 语义断言。

    返回 Verdict 对象：
      - bool(verdict) 只有 pass 为 True，可直接 assert
      - .verdict / .confidence / .reason 可细分处理 uncertain
    """

    def _assert(response_data, expectation: str) -> Verdict:
        verdict = ai_oracle.judge_expectation(response_data, expectation)
        # 挂到 user_properties 上，junitxml 报告里能看到判定依据
        request.node.user_properties.append(
            ("ai_assert", f"{verdict.verdict}|{verdict.confidence:.2f}|{verdict.reason}")
        )
        return verdict

    return _assert

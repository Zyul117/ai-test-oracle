"""
端到端演示 —— 发请求 → 分层判定 → 出报告

先起 mock server：
    python mock_server.py

再跑：
    python demo.py

没配 OPENAI_API_KEY 时只跑 Layer 1（结构校验），配了则两层都跑。
"""

import sys

from ai_oracle import (
    FAIL,
    LayeredOracle,
    PASS,
    ReportGenerator,
    RequestRunner,
    SchemaValidator,
    UNCERTAIN,
    has_api_key,
)

BASE_URL = "http://127.0.0.1:8000"

BADGE = {PASS: "[PASS]", FAIL: "[FAIL]", UNCERTAIN: "[????]"}

# 每条用例：路径 + 接口定义 + 这条数据实际上对不对（用于对照演示效果）
CASES = [
    {
        "test_name": "正常用户信息",
        "path": "/api/user/1",
        "api_spec": "查询用户。返回 user_id(int)、name(str)、email(str)、"
                    "balance(float，账户余额，不应为负)。",
        "schema": {"type": "object", "required": ["user_id", "name", "email"]},
        "truth": "数据正常",
    },
    {
        "test_name": "余额为负（结构合法）",
        "path": "/api/user/2",
        "api_spec": "查询用户。balance 为账户余额，业务上不允许为负数。",
        "schema": {"type": "object", "required": ["user_id", "name", "email"]},
        "truth": "余额 -500，应判 fail",
    },
    {
        "test_name": "缺少必填字段 email",
        "path": "/api/user/3",
        "api_spec": "查询用户。user_id、name、email 均为必填字段。",
        "schema": {"type": "object", "required": ["user_id", "name", "email"]},
        "truth": "缺 email，Schema 层应拦住",
    },
    {
        "test_name": "订单金额不自洽（Layer 1 抓不到）",
        "path": "/api/order/1002",
        "api_spec": "查询订单。total 应等于所有 items 的 price × qty 之和。",
        "schema": {"type": "object", "required": ["order_id", "items", "total"]},
        "truth": "50×3=150 但 total=100，只能靠 Layer 2",
    },
    {
        "test_name": "订单状态自相矛盾（Layer 1 抓不到）",
        "path": "/api/order/1003",
        "api_spec": "查询订单。status 为订单状态；cancelled 表示是否已取消。"
                    "已取消的订单不应处于 shipped 状态。",
        "schema": {"type": "object", "required": ["order_id", "status"]},
        "truth": "cancelled=True 却 status=shipped，只能靠 Layer 2",
    },
    {
        "test_name": "分页 total 与列表不符",
        "path": "/api/product/list",
        "api_spec": "商品列表。total 为总记录数，items 为当前页数据。",
        "schema": {"type": "object", "required": ["page", "total", "items"]},
        "truth": "total=25 但 items 为空",
    },
]


def main():
    live = has_api_key()

    print("=" * 66)
    print("  AI Test Oracle — 端到端演示")
    print("=" * 66)
    print(f"  目标服务 : {BASE_URL}")
    print(f"  判定模式 : {'Layer 1 + Layer 2（LLM）' if live else 'Layer 1 only（未配置 API Key）'}")
    print("=" * 66)

    runner = RequestRunner(BASE_URL)
    layered = LayeredOracle() if live else None
    schema_only = SchemaValidator()
    results = []

    for i, case in enumerate(CASES, 1):
        print(f"\n[{i}/{len(CASES)}] {case['test_name']}")
        print(f"        预期 : {case['truth']}")

        resp = runner.run({"test_name": case["test_name"],
                           "method": "GET", "path": case["path"]})

        if not resp.ok:
            print(f"        请求失败 : {resp.error}")
            print("        （请先运行 python mock_server.py）")
            sys.exit(1)

        print(f"        响应 : HTTP {resp.status_code}  {resp.response_time_ms} ms")
        print(f"               {_short(resp.response_body)}")

        if live:
            outcome = layered.validate(
                api_spec=case["api_spec"],
                request_info={"method": "GET", "path": case["path"]},
                response_body=resp.response_body,
                status_code=resp.status_code,
                response_schema=case["schema"],
            )
            l1, l2, final = outcome["layer1"], outcome["layer2"], outcome["final"]

            print(f"        Layer 1 : {BADGE[l1.verdict]} {l1.reason}")
            for issue in l1.detail.get("issues", [])[:3]:
                print(f"                  - {issue}")

            if l2 is None:
                print("        Layer 2 : 已跳过（Layer 1 发现问题，省一次 LLM 调用）")
            else:
                print(f"        Layer 2 : {BADGE[l2.verdict]} ({l2.confidence:.0%}) {l2.reason}")
        else:
            final = schema_only.validate(resp.response_body, case["schema"])
            print(f"        Layer 1 : {BADGE[final.verdict]} {final.reason}")
            for issue in final.detail.get("issues", [])[:3]:
                print(f"                  - {issue}")

        results.append({"test_name": case["test_name"], "verdict": final})

    print()
    reporter = ReportGenerator()
    print(reporter.to_text(reporter.summarize(results)))

    if not live:
        print("\n提示：配置 OPENAI_API_KEY 后重跑，可看到 Layer 2 抓出")
        print("      「订单金额不自洽」「状态自相矛盾」这类 Schema 校验挡不住的问题。")


def _short(body, limit: int = 90) -> str:
    text = str(body)
    return text if len(text) <= limit else text[:limit] + " …"


if __name__ == "__main__":
    main()

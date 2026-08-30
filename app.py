"""
AI Test Oracle — Web 界面

启动：
    pip install -e ".[web]"
    streamlit run app.py

三步流程：配置接口 → 执行判定 → 看报告
"""

import json
import os

import streamlit as st

from ai_oracle import (
    FAIL,
    LayeredOracle,
    LLMClient,
    LLMOracle,
    PASS,
    ReportGenerator,
    RequestRunner,
    SchemaValidator,
    UNCERTAIN,
)

st.set_page_config(page_title="AI Test Oracle", page_icon="🔍", layout="wide")

_BADGE = {PASS: "✅ 通过", FAIL: "❌ 疑似 Bug", UNCERTAIN: "❓ 不确定"}

# 示例场景：把「路径 + 接口定义 + Schema」绑在一起切换。
# 否则改了路径忘了改 Schema，Layer 1 会因为「缺 user_id」这类无关原因报错。
PRESETS = {
    "余额为负（Layer 1 可抓）": {
        "path": "/api/user/2",
        "spec": "查询用户信息。返回 user_id(int)、name(str)、email(str)、"
                "balance(float，账户余额，业务上不允许为负)。",
        "schema": {"type": "object", "required": ["user_id", "name", "email"]},
    },
    "缺少必填字段（Layer 1 可抓）": {
        "path": "/api/user/3",
        "spec": "查询用户信息。user_id、name、email 均为必填字段。",
        "schema": {"type": "object", "required": ["user_id", "name", "email"]},
    },
    "订单金额不自洽（需 Layer 2）": {
        "path": "/api/order/1002",
        "spec": "查询订单。total 应等于所有 items 的 price × qty 之和。",
        "schema": {"type": "object", "required": ["order_id", "items", "total"]},
    },
    "订单状态矛盾（需 Layer 2）": {
        "path": "/api/order/1003",
        "spec": "查询订单。status 为订单状态，cancelled 表示是否已取消。"
                "已取消的订单不应处于 shipped（已发货）状态。",
        "schema": {"type": "object", "required": ["order_id", "status"]},
    },
    "正常数据（应判通过）": {
        "path": "/api/user/1",
        "spec": "查询用户信息。返回 user_id、name、email、balance。",
        "schema": {"type": "object", "required": ["user_id", "name", "email"]},
    },
}


# ----------------------------------------------------------------------
# 侧边栏：LLM 配置
# ----------------------------------------------------------------------
def sidebar_config():
    st.sidebar.header("LLM 配置")

    base_url = st.sidebar.text_input(
        "Base URL", value=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1"),
        help="OpenAI 兼容接口，DeepSeek / 通义千问 / GLM 都可以",
    )
    model = st.sidebar.text_input("模型", value=os.getenv("LLM_MODEL", "deepseek-chat"))
    api_key = st.sidebar.text_input(
        "API Key", value=os.getenv("OPENAI_API_KEY", ""), type="password"
    )

    if not api_key:
        st.sidebar.warning("未填 API Key —— 只能跑第一层 Schema 校验")
    else:
        st.sidebar.success("已配置，两层判定都可用")

    st.sidebar.divider()
    st.sidebar.caption(
        "**判定分两层**\n\n"
        "Layer 1 jsonschema 结构校验 — 零成本、确定性\n\n"
        "Layer 2 LLM 语义判断 — 结构通过后才调，省 token"
    )
    return base_url, model, api_key


# ----------------------------------------------------------------------
def render_verdict(verdict, title: str):
    """统一渲染一个判定结果"""
    label = _BADGE.get(verdict.verdict, verdict.verdict)
    st.markdown(f"**{title}**：{label}　置信度 {verdict.confidence:.0%}")
    if verdict.reason:
        st.caption(verdict.reason)

    issues = verdict.detail.get("issues") or []
    if issues:
        for issue in issues:
            st.markdown(f"- {issue}")

    extra = {k: v for k, v in verdict.detail.items() if k not in ("issues", "layer")}
    if extra:
        with st.expander("LLM 推理细节"):
            st.json(extra)


# ----------------------------------------------------------------------
def main():
    st.title("🔍 AI Test Oracle")
    st.caption(
        "用大模型判断 API 返回结果对不对 —— 解决传统断言只能验证预设规则、"
        "覆盖不到业务语义缺陷的问题（Oracle Problem）"
    )

    base_url, model, api_key = sidebar_config()

    tab_run, tab_assert = st.tabs(["完整流程（发请求 + 分层判定）", "单次语义断言"])

    # ------------------------------------------------------------------
    with tab_run:
        preset_name = st.selectbox(
            "示例场景", list(PRESETS.keys()),
            help="切换后会同步填好路径、接口定义和 Schema；也可以自己改",
        )
        preset = PRESETS[preset_name]

        col1, col2 = st.columns(2)

        with col1:
            base = st.text_input("服务地址", value="http://127.0.0.1:8000",
                                 help="可先运行 python mock_server.py 起本地 mock")
            method = st.selectbox("方法", ["GET", "POST", "PUT", "DELETE"])
            # key 带上场景名，切换场景时输入框会重置为该场景的默认值
            path = st.text_input("路径", value=preset["path"],
                                 key=f"path::{preset_name}")
            body_text = st.text_area("请求体（JSON，可空）", value="", height=80)

        with col2:
            api_spec = st.text_area(
                "接口定义", height=120, value=preset["spec"],
                key=f"spec::{preset_name}",
            )
            schema_text = st.text_area(
                "响应 Schema（JSON，留空则跳过 jsonschema 校验）", height=120,
                value=json.dumps(preset["schema"], ensure_ascii=False, indent=2),
                key=f"schema::{preset_name}",
            )

        if st.button("执行判定", type="primary"):
            body = _safe_json(body_text)
            schema = _safe_json(schema_text)

            with st.spinner("发送请求…"):
                result = RequestRunner(base).run({
                    "test_name": f"{method} {path}", "method": method,
                    "path": path, "body": body,
                })

            if not result.ok:
                st.error(f"请求失败：{result.error}")
                return

            st.success(f"HTTP {result.status_code}　{result.response_time_ms} ms")
            with st.expander("响应体", expanded=True):
                st.json(result.response_body)

            # 没 Key 时只跑 Layer 1，避免无意义的失败调用
            if not api_key:
                v = SchemaValidator().validate(result.response_body, schema)
                st.info("未配置 API Key，仅执行 Layer 1")
                render_verdict(v, "Layer 1 结构校验")
                return

            _apply_env(api_key, base_url, model)
            with st.spinner("LLM 语义判定中…"):
                outcome = LayeredOracle(LLMOracle(LLMClient(api_key, base_url, model))).validate(
                    api_spec=api_spec,
                    request_info={"method": method, "path": path, "body": body},
                    response_body=result.response_body,
                    status_code=result.status_code,
                    response_schema=schema,
                )

            render_verdict(outcome["layer1"], "Layer 1 结构校验")
            if outcome["layer2"] is None:
                st.info("Layer 1 已发现问题，跳过 LLM 调用（省 token）")
            else:
                st.divider()
                render_verdict(outcome["layer2"], "Layer 2 语义判断")

            st.divider()
            summary = ReportGenerator().summarize(
                [{"test_name": f"{method} {path}", "verdict": outcome["final"]}]
            )
            st.code(ReportGenerator().to_text(summary), language=None)

    # ------------------------------------------------------------------
    with tab_assert:
        st.caption("等价于 pytest 里的 `ai_assert(响应, 期望)`")
        resp_text = st.text_area(
            "响应 JSON", height=140,
            value=json.dumps({"order_id": 1002,
                              "items": [{"price": 50.0, "qty": 3}],
                              "total": 100.0}, ensure_ascii=False, indent=2),
        )
        expectation = st.text_area(
            "期望（自然语言）", height=80,
            value="订单 total 应该等于所有 items 的 price × qty 之和",
        )

        if st.button("语义判定", type="primary", key="assert_btn"):
            if not api_key:
                st.error("这一页必须配置 API Key")
                return
            _apply_env(api_key, base_url, model)
            with st.spinner("判定中…"):
                v = LLMOracle(LLMClient(api_key, base_url, model)).judge_expectation(
                    _safe_json(resp_text), expectation
                )
            render_verdict(v, "语义断言")


def _safe_json(text: str):
    """空文本返回 None，解析失败给提示而不是崩掉"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        st.warning(f"JSON 解析失败，已按空处理：{e}")
        return None


def _apply_env(api_key: str, base_url: str, model: str):
    """回填环境变量，让底层默认构造也能拿到界面上的配置"""
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["LLM_MODEL"] = model


if __name__ == "__main__":
    main()

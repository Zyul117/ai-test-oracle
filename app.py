"""
AI Test Oracle — Streamlit 前端界面
"""

import streamlit as st
import json
import time
from src.llm_client import LLMClient
from src.llm_oracle import LLMOracle
from src.schema_validator import SchemaValidator
from src.input_generator import InputGenerator
from src.request_runner import RequestRunner
from src.comparator import LayeredComparator
from src.report import ReportGenerator

# ── 页面配置 ─────────────────────────────────
st.set_page_config(
    page_title="AI Test Oracle",
    page_icon="🔮",
    layout="wide",
)
st.title("🔮 AI Test Oracle — 智能接口测试预言机")
st.caption("解决测试中的 Oracle Problem：自动判断 API 返回结果是否正确")

# ── 侧边栏：配置区 ──────────────────────────
with st.sidebar:
    st.header("⚙️ 配置")

    # API 地址
    base_url = st.text_input(
        "目标 API 地址",
        value="https://jsonplaceholder.typicode.com",
        help="你要测试的 API 基础地址",
    )

    # LLM 配置
    st.subheader("🤖 LLM 配置")
    st.caption("使用兼容 OpenAI 接口的模型均可")
    st.caption("支持 DeepSeek / 通义千问 / GLM / GPT 等")

    with st.expander("查看/修改 LLM 设置"):
        api_key = st.text_input("API Key", type="password", value="sk-your-key")
        base_url_llm = st.text_input("Base URL", value="https://api.openai.com/v1")
        model = st.text_input("Model", value="gpt-4o-mini")

    # 参数定义
    st.subheader("📋 测试参数定义")
    st.caption("粘贴 JSON 格式的参数列表，或使用示例")

    default_params = json.dumps(
        [
            {"name": "userId", "type": "integer", "in": "query", "minimum": 1, "maximum": 10},
            {"name": "id", "type": "integer", "in": "query", "minimum": 1, "maximum": 100},
        ],
        ensure_ascii=False,
        indent=2,
    )
    params_json = st.text_area("参数定义 (JSON)", value=default_params, height=200)

    st.divider()
    st.caption("💡 提示：本项目解决的是测试中的 Oracle Problem")
    st.caption("—— 如何自动判断测试结果是正确的？")

# ── 主区域：三个标签页 ──────────────────────
tab1, tab2, tab3 = st.tabs(["📝 定义接口 & 生成用例", "▶️ 执行测试", "📊 测试报告"])

# ── Tab 1: 接口定义 & 生成用例 ───────────────
with tab1:
    st.subheader("第一步：描述你要测试的接口")

    col1, col2 = st.columns(2)

    with col1:
        api_method = st.selectbox("HTTP 方法", ["GET", "POST", "PUT", "DELETE"])
        api_path = st.text_input("接口路径", value="/posts")

    with col2:
        st.caption("接口描述（告诉 LLM 这个接口是干什么的）")
        api_description = st.text_area(
            "接口功能描述",
            value="获取用户的所有帖子。支持通过 userId 筛选某个用户的帖子。返回帖子列表，每个帖子包含 userId, id, title, body。",
            height=120,
        )

    with st.expander("📄 响应 Schema（可选，用于 Layer 1 结构校验）"):
        default_schema = json.dumps(
            {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "integer"},
                        "id": {"type": "integer"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["userId", "id", "title", "body"],
                },
            },
            indent=2,
        )
        schema_json = st.text_area("JSON Schema", value=default_schema, height=200)
        response_schema = None
        try:
            response_schema = json.loads(schema_json)
        except json.JSONDecodeError:
            st.warning("Schema JSON 格式不正确，Layer 1 校验将跳过")

    # 对接下来的操作放 session_state
    if "cases" not in st.session_state:
        st.session_state.cases = []
    if "api_spec_text" not in st.session_state:
        st.session_state.api_spec_text = ""

    if st.button("🚀 Step 1: 生成测试用例", type="primary"):
        # 解析参数
        try:
            params_definition = json.loads(params_json)
        except json.JSONDecodeError:
            st.error("参数定义 JSON 格式错误，请检查")
            params_definition = []

        # 生成测试用例
        generator = InputGenerator()
        base_request = {
            "method": api_method,
            "path": api_path,
            "headers": {"Content-Type": "application/json"},
            "params": {},
            "body": None,
        }
        cases = generator.generate(params_definition, base_request)

        # 构建接口描述全文
        api_spec_text = f"""接口功能: {api_description}
HTTP 方法: {api_method}
接口路径: {api_path}
预期返回: {schema_json[:300]}"""

        st.session_state.cases = cases
        st.session_state.api_spec_text = api_spec_text

        st.success(f"✅ 生成了 {len(cases)} 个测试用例")

    if st.session_state.cases:
        st.subheader(f"生成的测试用例 ({len(st.session_state.cases)} 个)")
        for i, case in enumerate(st.session_state.cases):
            with st.expander(f"用例 {i+1}: {case.get('test_name', '?')}"):
                st.json(case)

# ── Tab 2: 执行测试 ──────────────────────────
with tab2:
    st.subheader("第二步：执行测试并启动 AI Oracle")

    if not st.session_state.cases:
        st.info("👈 请先在 Tab 1 中生成测试用例")
    else:
        if st.button("▶️ Step 2: 执行全部测试 & AI 判断", type="primary"):
            # 初始化组件
            runner = RequestRunner(base_url)
            llm_client = LLMClient()
            # 如果用户在侧边栏填了配置，覆盖默认
            if api_key != "sk-your-key":
                import os
                os.environ["OPENAI_API_KEY"] = api_key
                os.environ["OPENAI_BASE_URL"] = base_url_llm
                os.environ["LLM_MODEL"] = model
                llm_client = LLMClient()

            oracle = LLMOracle(llm_client)
            comparator = LayeredComparator(oracle)
            report_gen = ReportGenerator()

            results = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, case in enumerate(st.session_state.cases):
                test_name = case.get("test_name", f"用例{i+1}")
                status_text.text(f"执行中: {test_name} ({i+1}/{len(st.session_state.cases)})")

                # 执行请求
                exec_result = runner.run(case)

                # 分层判断
                if exec_result.error:
                    # 网络错误等异常
                    oracle_result = {
                        "test_name": test_name,
                        "final_verdict": f"ERROR — {exec_result.error}",
                        "findings_detail": [{
                            "layer": "请求执行层",
                            "verdict": "error",
                            "detail": exec_result.error,
                        }],
                    }
                elif exec_result.response_body is None:
                    oracle_result = {
                        "test_name": test_name,
                        "final_verdict": "ERROR — 无响应体",
                        "findings_detail": [],
                    }
                else:
                    # 构建请求信息
                    request_info = {
                        "method": case.get("method", "GET"),
                        "path": case.get("path", "/"),
                        "params": case.get("params", {}),
                        "body": case.get("body"),
                    }
                    oracle_result = comparator.validate(
                        api_spec=st.session_state.api_spec_text,
                        request_info=request_info,
                        response_body=exec_result.response_body,
                        status_code=exec_result.status_code or 0,
                        response_schema=response_schema,
                    )

                oracle_result["test_name"] = test_name
                oracle_result["status_code"] = exec_result.status_code
                oracle_result["response_time_ms"] = exec_result.response_time_ms
                oracle_result["response_body_preview"] = json.dumps(
                    exec_result.response_body, ensure_ascii=False
                )[:300] if exec_result.response_body else "(无)"
                results.append(oracle_result)

                progress_bar.progress((i + 1) / len(st.session_state.cases))
                time.sleep(0.1)  # 稍微放慢，避免进度条闪太快

            status_text.text("✅ 完成！")
            st.session_state.results = results
            st.session_state.summary = report_gen.generate_summary(results)

        # 展示结果
        if "results" in st.session_state:
            st.subheader("🔍 AI Oracle 逐条判断结果")
            for r in st.session_state.results:
                verdict = r.get("final_verdict", "?")
                if verdict.startswith("PASS"):
                    icon = "✅"
                elif verdict.startswith("FAIL"):
                    icon = "❌"
                elif verdict.startswith("ERROR"):
                    icon = "💥"
                else:
                    icon = "❓"

                with st.expander(f"{icon} {r.get('test_name', '?')} — HTTP {r.get('status_code', '?')} ({r.get('response_time_ms', 0)}ms)"):
                    st.markdown(f"**最终判断:** {verdict}")
                    st.text(f"响应预览: {r.get('response_body_preview', '')}")

                    # 展示各层详情
                    l1 = r.get("layer1")
                    l2 = r.get("layer2")
                    if l1:
                        st.caption(f"Layer 1 (Schema): {'✅ 通过' if l1.get('passed') else '❌ 失败'}")
                        for issue in l1.get("issues", []):
                            st.caption(f"  - {issue}")
                    if l2:
                        st.caption(f"Layer 2 (LLM Oracle): {l2.get('verdict', '?')} (置信度: {l2.get('confidence', 0):.0%})")
                        st.caption(f"  AI判断: {l2.get('summary', '')}")

                    if r.get("cost_notes"):
                        for note in r.get("cost_notes", []):
                            st.caption(f"  💰 {note}")

# ── Tab 3: 报告 ──────────────────────────────
with tab3:
    st.subheader("第三步：查看测试报告")

    if "summary" not in st.session_state:
        st.info("👈 请先在 Tab 2 中执行测试")
    else:
        summary = st.session_state.summary

        # 指标卡片
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("总用例", summary["total"])
        col2.metric("✅ 通过", summary["pass"])
        col3.metric("❌ 失败", summary["fail"], delta=f"-{summary['fail']}" if summary['fail'] else None)
        col4.metric("❓ 不确定", summary["uncertain"])

        st.progress(summary["pass"] / max(summary["total"], 1))
        st.caption(f"通过率: {summary['pass_rate']}")

        # 疑似 Bug 列表
        if summary.get("errors"):
            st.subheader("🔴 疑似 Bug")
            for i, err in enumerate(summary["errors"], 1):
                with st.expander(f"Bug #{i}: {err.get('test_name', '')}"):
                    for f in err.get("findings", []):
                        st.markdown(f"**{f.get('layer', '')}**: {f.get('detail', '')}")

        # 导出按钮
        if st.button("📥 导出文本报告"):
            report_gen = ReportGenerator()
            text_report = report_gen.generate_text_report(summary)
            st.download_button(
                label="下载报告",
                data=text_report,
                file_name="ai_oracle_report.txt",
                mime="text/plain",
            )
            st.code(text_report)

        st.divider()
        st.caption("🔮 AI Test Oracle — 用 AI 解决测试中的 Oracle Problem")

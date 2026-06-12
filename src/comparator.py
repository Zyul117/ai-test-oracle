"""
分层判断引擎
Layer 1: Schema 校验（零成本，100% 准确）
Layer 2: LLM Oracle 语义判断（发现隐性 Bug）
"""

from src.schema_validator import SchemaValidator
from src.llm_oracle import LLMOracle


class LayeredComparator:
    """
    两层判断策略：
    - 第一层：Schema 结构性校验，用 jsonschema 库，不需要 LLM
    - 第二层：如果 Schema 通过，再调用 LLM Oracle 做语义级判断
    """

    def __init__(self, llm_oracle: LLMOracle):
        self.schema_validator = SchemaValidator()
        self.oracle = llm_oracle

    def validate(
        self,
        api_spec: str,
        request_info: dict,
        response_body: dict,
        status_code: int,
        response_schema: dict = None,
    ) -> dict:
        """
        完整的两层判断流程
        Args:
            api_spec: 接口文档描述
            request_info: 请求信息
            response_body: 响应体
            status_code: HTTP 状态码
            response_schema: 可选的 JSON Schema 定义
        Returns:
            {"layer1": {...}, "layer2": {...}, "final_verdict": "...", "findings_summary": "..."}
        """
        findings = []
        cost_notes = []

        # ---- Layer 1: Schema 校验 ----
        if response_schema:
            l1_result = self.schema_validator.validate(response_body, response_schema)
            cost_notes.append("Layer1 (Schema): 零成本，零幻觉")
        else:
            # 没有 Schema 时，做基础检查
            l1_result = {"passed": True, "issues": [], "note": "未提供 Schema，跳过"}
            cost_notes.append("Layer1 (Schema): 跳过（无 Schema 定义）")

        if not l1_result.get("passed"):
            findings.append({
                "layer": "Layer 1 — Schema 校验",
                "verdict": "fail",
                "confidence": 1.0,
                "detail": l1_result.get("issues", []),
            })
            # Schema 层已经发现问题，直接返回
            return {
                "layer1": l1_result,
                "layer2": None,
                "final_verdict": "FAIL — 响应结构不符合接口定义",
                "findings_detail": findings,
                "cost_notes": cost_notes,
            }

        # ---- Layer 2: LLM Oracle 语义判断 ----
        l2_result = self.oracle.judge(api_spec, request_info, response_body, status_code)
        cost_notes.append("Layer2 (LLM): 消耗 ~1K tokens，可能存在幻觉")

        oracle_verdict = l2_result.get("verdict", "uncertain")
        confidence = l2_result.get("confidence", 0)

        if oracle_verdict == "fail":
            findings.append({
                "layer": "Layer 2 — LLM 语义判断",
                "verdict": "fail",
                "confidence": confidence,
                "detail": l2_result,
            })
            final = f"FAIL — LLM Oracle 检测到可能的 Bug（置信度 {confidence:.0%}）"
        elif oracle_verdict == "uncertain":
            findings.append({
                "layer": "Layer 2 — LLM 语义判断",
                "verdict": "uncertain",
                "confidence": confidence,
                "detail": l2_result.get("summary", ""),
            })
            final = "UNCERTAIN — 信息不足以判断，建议人工审查"
        else:
            findings.append({
                "layer": "Layer 2 — LLM 语义判断",
                "verdict": "pass",
                "confidence": confidence,
                "detail": l2_result.get("summary", ""),
            })
            final = "PASS — Schema 和语义检查均通过"

        return {
            "layer1": l1_result,
            "layer2": l2_result,
            "final_verdict": final,
            "findings_detail": findings,
            "cost_notes": cost_notes,
        }

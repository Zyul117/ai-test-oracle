"""
分层判定引擎

Layer 1 — Schema 结构校验：用 jsonschema，零成本、零幻觉、100% 可复现
Layer 2 — LLM 语义判断：结构没问题时才调，发现业务逻辑层面的隐性 Bug

分层的意义是省钱也省误判：结构性问题（字段缺失、类型不对）根本不需要
LLM 参与，Layer 1 挡掉后直接返回，不再产生 token 消耗。
"""

import jsonschema
from jsonschema import ValidationError

from .oracle import LLMOracle
from .verdict import FAIL, PASS, UNCERTAIN, Verdict

# 命名上带金额语义的字段，出现负数基本可以判定异常
_AMOUNT_KEYS = ("price", "amount", "total", "balance", "cost", "fee")
# 命名上是集合的字段，为空往往意味着数据缺失或查询条件有误
_COLLECTION_KEYS = ("items", "data", "results", "records", "list")


class SchemaValidator:
    """第一层：结构校验"""

    def validate(self, response_body, response_schema: dict = None) -> Verdict:
        issues = []

        if response_schema:
            try:
                jsonschema.validate(instance=response_body, schema=response_schema)
            except ValidationError as e:
                # jsonschema 的报错很技术化，转成能直接看懂的描述
                path = " → ".join(str(p) for p in e.absolute_path) or "根对象"
                issues.append(f"字段 [{path}] 校验失败: {e.message}")

        self._extra_checks(response_body, issues)

        if issues:
            return Verdict(
                verdict=FAIL,
                confidence=1.0,     # 结构校验是确定性的，不存在置信度问题
                reason=f"结构校验发现 {len(issues)} 个问题",
                detail={"layer": "schema", "issues": issues},
            )

        note = "结构校验通过" if response_schema else "未提供 Schema，仅做通用检查"
        return Verdict(verdict=PASS, confidence=1.0, reason=note,
                       detail={"layer": "schema", "issues": []})

    def _extra_checks(self, body, issues: list):
        """不依赖 Schema 的通用检查，支持 dict 与 list"""
        if isinstance(body, list):
            if not body:
                issues.append("返回了空数组，可能数据缺失或查询条件有误")
            for i, item in enumerate(body):
                if isinstance(item, dict):
                    self._check_fields(item, issues, prefix=f"数组第 {i} 项的字段")
        elif isinstance(body, dict):
            self._check_fields(body, issues, prefix="字段")

    @staticmethod
    def _check_fields(data: dict, issues: list, prefix: str):
        for key, value in data.items():
            name = f"{prefix} {key}"

            if value is None:
                issues.append(f"{name} 的值为 null，可能是数据缺失")

            if key.lower() in _AMOUNT_KEYS and isinstance(value, (int, float)) \
                    and not isinstance(value, bool) and value < 0:
                issues.append(f"{name} 为负数（{value}），可能异常")

            if key.lower() in _COLLECTION_KEYS and isinstance(value, list) and not value:
                issues.append(f"{name} 为空，可能数据缺失或查询条件有误")


class LayeredOracle:
    """把两层串起来，对外只暴露一个 validate()"""

    def __init__(self, oracle: LLMOracle = None):
        self.schema_validator = SchemaValidator()
        self.oracle = oracle or LLMOracle()

    def validate(self, api_spec: str, request_info: dict, response_body,
                 status_code: int, response_schema: dict = None) -> dict:
        """
        返回 {"layer1": Verdict, "layer2": Verdict|None, "final": Verdict}
        Layer 1 不通过时 layer2 为 None —— 省掉一次 LLM 调用。
        """
        layer1 = self.schema_validator.validate(response_body, response_schema)

        if layer1.verdict == FAIL:
            return {"layer1": layer1, "layer2": None, "final": layer1}

        layer2 = self.oracle.judge_response(
            api_spec, request_info, response_body, status_code
        )

        final = Verdict(
            verdict=layer2.verdict,
            confidence=layer2.confidence,
            reason=self._describe(layer2),
            detail={"layer": "schema+llm", **layer2.detail},
        )
        return {"layer1": layer1, "layer2": layer2, "final": final}

    @staticmethod
    def _describe(layer2: Verdict) -> str:
        if layer2.verdict == FAIL:
            return f"LLM 判定存在疑似 Bug（置信度 {layer2.confidence:.0%}）：{layer2.reason}"
        if layer2.verdict == UNCERTAIN:
            return f"信息不足，建议人工复核：{layer2.reason}"
        return f"结构与语义检查均通过：{layer2.reason}"

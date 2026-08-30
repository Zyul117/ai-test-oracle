"""
核心逻辑测试 —— 全部不需要 API Key，CI 里直接跑

覆盖三块合并时重点处理的逻辑：
1. Verdict 契约容错（原来两个项目字段名不一致导致 KeyError）
2. 三级 JSON 降级解析（LLM 不按格式输出是常态）
3. Layer 1 结构校验（零成本、确定性）
"""

import pytest

from ai_oracle import (
    FAIL,
    PASS,
    UNCERTAIN,
    ReportGenerator,
    SchemaValidator,
    Verdict,
    parse_json_response,
)


# ======================================================================
# Verdict 三态契约
# ======================================================================

class TestVerdict:

    def test_normal_fields(self):
        v = Verdict.from_dict({"verdict": "pass", "confidence": 0.9, "reason": "正常"})
        assert v.verdict == PASS
        assert v.confidence == 0.9
        assert v.reason == "正常"

    def test_accepts_legacy_summary_field(self):
        """Web 侧历史字段名是 summary，插件侧是 reason，两个都要认"""
        v = Verdict.from_dict({"verdict": "fail", "summary": "余额为负"})
        assert v.verdict == FAIL
        assert v.reason == "余额为负"

    def test_missing_fields_do_not_raise(self):
        """合并前插件直接取 result_dict["reason"]，少字段就 KeyError"""
        v = Verdict.from_dict({"verdict": "pass"})
        assert v.verdict == PASS
        assert v.confidence == 0.0
        assert v.reason == ""

    @pytest.mark.parametrize("bad", ["passed", "失败", "PASS_WITH_WARNING", "", None])
    def test_illegal_verdict_degrades_to_uncertain(self, bad):
        """模型偶尔不按枚举返回，一律降级 uncertain 而不是当成 pass"""
        assert Verdict.from_dict({"verdict": bad}).verdict == UNCERTAIN

    @pytest.mark.parametrize("raw,expected", [
        (1.5, 1.0), (-0.3, 0.0), ("0.7", 0.7), ("abc", 0.0), (None, 0.0),
    ])
    def test_confidence_is_clamped(self, raw, expected):
        assert Verdict.from_dict({"verdict": "pass", "confidence": raw}).confidence == expected

    def test_non_dict_input(self):
        assert Verdict.from_dict(["not", "a", "dict"]).verdict == UNCERTAIN

    def test_bool_semantics(self):
        """只有 pass 为真 —— uncertain 不能当通过"""
        assert bool(Verdict(verdict=PASS))
        assert not bool(Verdict(verdict=FAIL))
        assert not bool(Verdict(verdict=UNCERTAIN))

    def test_extra_fields_kept_in_detail(self):
        v = Verdict.from_dict({
            "verdict": "fail", "reason": "x",
            "step1_data_check": {"passed": False}, "bug_hypothesis": "后端逻辑",
        })
        assert v.detail["bug_hypothesis"] == "后端逻辑"
        assert "step1_data_check" in v.detail


# ======================================================================
# 三级 JSON 降级解析
# ======================================================================

class TestJSONParsing:

    def test_level1_plain_json(self):
        assert parse_json_response('{"verdict": "pass"}')["verdict"] == "pass"

    def test_level2_fenced_block(self):
        raw = '分析如下：\n```json\n{"verdict": "fail"}\n```\n以上'
        assert parse_json_response(raw)["verdict"] == "fail"

    def test_level2_fence_without_lang(self):
        assert parse_json_response('```\n{"verdict": "pass"}\n```')["verdict"] == "pass"

    def test_level3_braces(self):
        raw = '结论：{"verdict": "uncertain", "confidence": 0.5}，供参考'
        assert parse_json_response(raw)["verdict"] == "uncertain"

    @pytest.mark.parametrize("raw", ["", None, "完全无法解析", "[1,2,3]", "{坏的"])
    def test_unparseable_returns_empty(self, raw):
        """解析不出来返回 {}，由 Verdict 决定兜底 —— 不抛异常"""
        assert parse_json_response(raw) == {}

    def test_end_to_end_fallback(self):
        """解析失败 → Verdict 兜底为 uncertain"""
        v = Verdict.from_dict(parse_json_response("模型今天不想输出 JSON"))
        assert v.verdict == UNCERTAIN


# ======================================================================
# Layer 1 结构校验
# ======================================================================

class TestSchemaValidator:

    def setup_method(self):
        self.sv = SchemaValidator()

    def test_valid_response_passes(self):
        v = self.sv.validate(
            {"name": "张三", "age": 25},
            {"type": "object", "required": ["name", "age"],
             "properties": {"age": {"type": "integer"}}},
        )
        assert v.verdict == PASS
        assert v.confidence == 1.0

    def test_missing_required_field_fails(self):
        v = self.sv.validate(
            {"name": "张三"},
            {"type": "object", "required": ["name", "email"]},
        )
        assert v.verdict == FAIL
        assert any("email" in i for i in v.detail["issues"])

    def test_wrong_type_fails(self):
        v = self.sv.validate(
            {"age": "二十五"},
            {"type": "object", "properties": {"age": {"type": "integer"}}},
        )
        assert v.verdict == FAIL

    def test_negative_amount_caught_without_schema(self):
        """没有 Schema 也能抓到负数金额 —— 这类是最典型的隐性 Bug"""
        v = self.sv.validate({"balance": -500})
        assert v.verdict == FAIL
        assert any("负数" in i for i in v.detail["issues"])

    def test_null_value_caught(self):
        v = self.sv.validate({"name": None})
        assert v.verdict == FAIL
        assert any("null" in i for i in v.detail["issues"])

    def test_empty_collection_caught(self):
        v = self.sv.validate({"items": []})
        assert v.verdict == FAIL

    def test_bool_is_not_treated_as_negative_amount(self):
        """False 在 Python 里 < 0 为假，但要确保 bool 不被当数字处理"""
        v = self.sv.validate({"total": True})
        assert not any("负数" in i for i in v.detail["issues"])

    def test_list_response_items_checked(self):
        v = self.sv.validate([{"price": -1}, {"price": 10}])
        assert v.verdict == FAIL
        assert any("负数" in i for i in v.detail["issues"])

    def test_empty_list_response_caught(self):
        assert self.sv.validate([]).verdict == FAIL

    def test_clean_response_passes(self):
        assert self.sv.validate({"user_id": 1, "balance": 100.0}).verdict == PASS


# ======================================================================
# 报告汇总
# ======================================================================

class TestReport:

    def test_summarize_counts(self):
        results = [
            {"test_name": "a", "verdict": Verdict(verdict=PASS)},
            {"test_name": "b", "verdict": Verdict(verdict=FAIL, reason="余额为负",
                                                  confidence=0.9)},
            {"test_name": "c", "verdict": Verdict(verdict=UNCERTAIN)},
            {"test_name": "d", "verdict": Verdict(verdict=PASS)},
        ]
        s = ReportGenerator().summarize(results)
        assert (s["total"], s["pass"], s["fail"], s["uncertain"]) == (4, 2, 1, 1)
        assert s["pass_rate"] == "50.0%"
        assert s["failures"][0]["test_name"] == "b"

    def test_empty_results(self):
        assert ReportGenerator().summarize([])["total"] == 0

    def test_text_report_contains_key_info(self):
        results = [{"test_name": "订单金额不自洽",
                    "verdict": Verdict(verdict=FAIL, reason="total 与明细不符",
                                       confidence=0.85)}]
        text = ReportGenerator().to_text(ReportGenerator().summarize(results))
        assert "订单金额不自洽" in text
        assert "total 与明细不符" in text

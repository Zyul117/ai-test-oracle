"""
三态判定契约

合并两个项目时发现的问题：原来 Web 应用侧返回的字段叫 summary，
pytest 插件侧叫 reason，插件里又直接用 result_dict["reason"] 取值——
LLM 少返一个字段就 KeyError。这里统一成一个 Verdict，
所有取值走 from_dict 兜底，不再直接索引。
"""

from dataclasses import dataclass, field

PASS = "pass"
FAIL = "fail"
UNCERTAIN = "uncertain"
_VALID = (PASS, FAIL, UNCERTAIN)


@dataclass
class Verdict:
    """一次判定的结果"""

    verdict: str = UNCERTAIN          # pass / fail / uncertain
    confidence: float = 0.0           # 0.0 ~ 1.0
    reason: str = ""                  # 判断依据（原 summary 字段统一到这里）
    detail: dict = field(default_factory=dict)   # CoT 各步骤等原始信息

    def __bool__(self) -> bool:
        """只有 pass 为真，fail 和 uncertain 都是假"""
        return self.verdict == PASS

    def __repr__(self) -> str:
        return f"<Verdict {self.verdict} ({self.confidence:.0%}) — {self.reason}>"

    @classmethod
    def from_dict(cls, data: dict) -> "Verdict":
        """
        从 LLM 返回的 dict 构造，容忍字段缺失与命名差异。
        LLM 不按格式输出是常态，所以这里不做任何强制索引。
        """
        if not isinstance(data, dict):
            return cls(reason="LLM 返回了非对象结构")

        verdict = str(data.get("verdict", UNCERTAIN)).strip().lower()
        if verdict not in _VALID:
            # 模型偶尔会返回 "passed" / "失败" 之类，一律降级为 uncertain
            verdict = UNCERTAIN

        # summary 和 reason 两个历史字段名都接受
        reason = data.get("reason") or data.get("summary") or ""

        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        # 除三个标准字段外的内容都留在 detail 里，便于排查
        detail = {k: v for k, v in data.items()
                  if k not in ("verdict", "confidence", "reason", "summary")}

        return cls(verdict=verdict, confidence=confidence,
                   reason=str(reason), detail=detail)

    @classmethod
    def error(cls, message: str) -> "Verdict":
        """LLM 调用失败等异常场景，一律返回 uncertain 而不是抛异常"""
        return cls(verdict=UNCERTAIN, confidence=0.0, reason=message)

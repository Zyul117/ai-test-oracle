"""
AI Test Oracle — 分层 API 测试预言机

两层判定：
  Layer 1  jsonschema 结构校验（零成本、零幻觉）
  Layer 2  LLM 语义判断（CoT 三步推理，发现结构校验挡不住的隐性 Bug）

两种用法共用同一套核心：
  - pytest 插件：fixture 注入 ai_assert，用自然语言写期望
  - Web / CLI  ：完整流程（发请求 → 分层判定 → 出报告）
"""

__version__ = "0.2.0"

from .layers import LayeredOracle, SchemaValidator
from .llm import LLMClient, has_api_key, parse_json_response
from .oracle import LLMOracle
from .report import ReportGenerator
from .runner import RequestRunner, TestResult
from .verdict import FAIL, PASS, UNCERTAIN, Verdict

__all__ = [
    "__version__",
    "Verdict",
    "PASS",
    "FAIL",
    "UNCERTAIN",
    "LLMClient",
    "has_api_key",
    "parse_json_response",
    "LLMOracle",
    "SchemaValidator",
    "LayeredOracle",
    "RequestRunner",
    "TestResult",
    "ReportGenerator",
]

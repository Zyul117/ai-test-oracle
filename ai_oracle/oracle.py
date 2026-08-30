"""
LLM 语义判定层（第二层）

两种判定模式共用同一个 LLM 客户端和同一套 JSON 容错解析：
- judge_response()：完整 CoT 三步推理，给接口定义+请求+响应，用于 Web/CLI 流程
- judge_expectation()：轻量断言，给自然语言期望+响应，用于 pytest 的 ai_assert

合并前这两种模式分散在两个项目里，各自维护一份 LLM 调用和解析逻辑。
"""

import json

from .llm import LLMClient, load_prompt, parse_json_response
from .verdict import Verdict


class LLMOracle:
    """LLM 测试预言机"""

    def __init__(self, client: LLMClient = None):
        self.llm = client or LLMClient()
        self._oracle_prompt = None
        self._assert_prompt = None

    # prompt 懒加载，避免只用其中一种模式时也读两个文件
    @property
    def oracle_prompt(self) -> str:
        if self._oracle_prompt is None:
            self._oracle_prompt = load_prompt("oracle_system.txt")
        return self._oracle_prompt

    @property
    def assert_prompt(self) -> str:
        if self._assert_prompt is None:
            self._assert_prompt = load_prompt("assert_system.txt")
        return self._assert_prompt

    # ------------------------------------------------------------------
    # 模式一：完整 CoT 判定（接口定义 + 请求 + 响应）
    # ------------------------------------------------------------------
    def judge_response(self, api_spec: str, request_info: dict,
                       response_body, status_code: int) -> Verdict:
        """
        判断一次 API 调用的结果是否正确。
        直接问"这个响应对不对"模型经常乱说，所以 prompt 里强制它按
        数据结构 → 业务逻辑 → 结论 三步推理。
        """
        user_input = self._build_oracle_input(
            api_spec, request_info, response_body, status_code
        )
        return self._ask(self.oracle_prompt, user_input, max_tokens=2000)

    # ------------------------------------------------------------------
    # 模式二：自然语言期望断言（用于 pytest ai_assert）
    # ------------------------------------------------------------------
    def judge_expectation(self, response_data, expectation: str) -> Verdict:
        """判断响应是否符合一段自然语言描述的期望"""
        user_input = (
            f"=== 期望描述 ===\n{expectation}\n\n"
            f"=== API 实际响应 ===\n{_dump(response_data)}"
        )
        return self._ask(self.assert_prompt, user_input, max_tokens=500)

    # ------------------------------------------------------------------
    def _ask(self, system_prompt: str, user_input: str, max_tokens: int) -> Verdict:
        """统一的调用 → 解析 → 构造 Verdict 通路"""
        try:
            raw = self.llm.chat(system_prompt, user_input, max_tokens=max_tokens)
        except Exception as e:
            # LLM 调用失败不让整轮测试崩掉，降级为 uncertain
            return Verdict.error(f"LLM 调用失败: {e}")

        parsed = parse_json_response(raw)
        if not parsed:
            v = Verdict.error("无法解析 LLM 回复")
            v.detail["raw_response"] = raw[:800]
            return v

        return Verdict.from_dict(parsed)

    @staticmethod
    def _build_oracle_input(api_spec: str, request_info: dict,
                            response_body, status_code: int) -> str:
        """拼装给 LLM 的输入"""
        parts = [
            "=== 接口定义 ===",
            api_spec or "（未提供接口定义）",
            "",
            "=== 实际请求 ===",
            f"方法: {request_info.get('method', 'GET')}",
            f"路径: {request_info.get('path', '/')}",
        ]
        if request_info.get("params"):
            parts.append(f"查询参数: {_dump(request_info['params'], indent=None)}")
        if request_info.get("body"):
            parts.append(f"请求体: {_dump(request_info['body'], indent=None)}")

        parts += [
            "",
            "=== 实际响应 ===",
            f"HTTP 状态码: {status_code}",
            f"响应体: {_dump(response_body)}",
        ]
        return "\n".join(parts)


def _dump(data, indent: int = 2) -> str:
    """序列化给 LLM 看，非 JSON 类型退化成 str"""
    try:
        return json.dumps(data, ensure_ascii=False, indent=indent)
    except (TypeError, ValueError):
        return str(data)

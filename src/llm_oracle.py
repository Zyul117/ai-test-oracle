"""
LLM 测试预言机 — 项目的核心模块
用大语言模型判断 API 返回结果是否正确

核心设计：
1. Chain-of-Thought：强制 AI 先推理数据结构，再检查业务逻辑，最后下结论
2. 结构化输出：用 Prompt 约束 JSON 格式，方便程序解析
3. 错误容忍：解析失败时有 fallback，不会让整个流程崩溃
"""

import json
import re
from pathlib import Path


class LLMOracle:
    """LLM 测试预言机"""

    def __init__(self, llm_client):
        self.llm = llm_client
        # 加载系统 Prompt
        prompt_path = Path(__file__).parent.parent / "prompts" / "oracle_system.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.system_prompt = f.read()

    def judge(
        self,
        api_spec: str,
        request_info: dict,
        response_body: dict,
        status_code: int,
    ) -> dict:
        """
        判断一次 API 调用的结果是否正确
        Args:
            api_spec: 接口的文本描述或 OpenAPI 定义
            request_info: 请求信息（method, url, params, body 等）
            response_body: API 返回的 JSON 响应
            status_code: HTTP 状态码
        Returns:
            判断结果字典，包含 verdict, confidence, summary 等
        """
        # 拼装用户输入
        user_input = self._build_input(api_spec, request_info, response_body, status_code)

        # 调用 LLM
        raw_response = self.llm.chat(self.system_prompt, user_input)

        # 解析结果
        return self._parse_response(raw_response)

    def _build_input(
        self,
        api_spec: str,
        request_info: dict,
        response_body: dict,
        status_code: int,
    ) -> str:
        """拼装给 LLM 的输入"""
        parts = []

        parts.append("=== 接口定义 ===")
        parts.append(api_spec)
        parts.append("")

        parts.append("=== 实际请求 ===")
        parts.append(f"方法: {request_info.get('method', 'GET')}")
        parts.append(f"路径: {request_info.get('path', '/')}")
        if request_info.get("params"):
            parts.append(f"查询参数: {json.dumps(request_info['params'], ensure_ascii=False)}")
        if request_info.get("body"):
            parts.append(f"请求体: {json.dumps(request_info['body'], ensure_ascii=False)}")
        parts.append("")

        parts.append("=== 实际响应 ===")
        parts.append(f"HTTP 状态码: {status_code}")
        parts.append(f"响应体: {json.dumps(response_body, ensure_ascii=False, indent=2)}")

        return "\n".join(parts)

    def _parse_response(self, raw_text: str) -> dict:
        """从 LLM 的回复中提取 JSON 结果"""
        # 兜底结果
        fallback = {
            "verdict": "uncertain",
            "confidence": 0.0,
            "summary": "无法解析 LLM 回复",
            "raw_response": raw_text[:500],
        }

        try:
            # 尝试直接解析整个回复
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", raw_text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取 { ... } 对象
        brace_start = raw_text.find("{")
        brace_end = raw_text.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                return json.loads(raw_text[brace_start : brace_end + 1])
            except json.JSONDecodeError:
                pass

        # 确实解析不了，返回兜底
        fallback["raw_response"] = raw_text[:800]
        return fallback

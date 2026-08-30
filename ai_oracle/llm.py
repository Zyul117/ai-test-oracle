"""
LLM 调用 + JSON 容错解析

合并前两个项目各写了一份几乎相同的实现（llm_client.py 和 ai_judge.py），
连环境变量和 temperature 都一样。这里合成唯一一份。

三级降级解析：直接 json.loads → 提取 ```json 代码块 → 提取最外层花括号 → 兜底。
因为 LLM 经常在 JSON 前后加解释性文字，直接解析会失败。
"""

import json
import os
import re
from pathlib import Path

from openai import OpenAI

PROMPT_DIR = Path(__file__).parent / "prompts"

# 无 Key 时 OpenAI SDK 会对着 api.openai.com 反复重试，导致 pytest 挂死几分钟。
# 合并前 pytest-ai-assert 就踩了这个坑（跑 tests/ 会卡住），所以显式限制。
_TIMEOUT_SEC = 30
_MAX_RETRIES = 1

_PLACEHOLDER_KEYS = ("", "sk-your-api-key-here", "sk-xxx")


def has_api_key() -> bool:
    """
    是否配置了真实可用的 API Key。
    用于给需要真实调用的测试加 skip 条件，避免无 Key 时挂死。
    """
    return os.getenv("OPENAI_API_KEY", "").strip() not in _PLACEHOLDER_KEYS


def load_prompt(name: str) -> str:
    """从 prompts/ 目录读取 system prompt"""
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def parse_json_response(raw_text: str) -> dict:
    """
    从 LLM 回复中提取 JSON，三级降级。
    解析不出来返回 {} —— 由调用方（Verdict.from_dict）决定兜底行为。
    """
    if not raw_text:
        return {}

    # 第一级：整个回复就是 JSON
    try:
        parsed = json.loads(raw_text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    # 第二级：藏在 ```json ... ``` 代码块里
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

    # 第三级：从第一个 { 到最后一个 }
    start, end = raw_text.find("{"), raw_text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(raw_text[start:end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

    return {}


class LLMClient:
    """OpenAI 兼容接口封装（DeepSeek / 通义千问 / GLM 等都可用）"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("LLM_MODEL", "gpt-4o-mini")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=_TIMEOUT_SEC,
            max_retries=_MAX_RETRIES,
        )

    def chat(self, system_prompt: str, user_input: str,
             temperature: float = 0.3, max_tokens: int = 2000) -> str:
        """
        发一次对话。测试场景要低 temperature 保证判定稳定。
        调用失败时抛异常，由上层转成 uncertain（不让整轮测试崩掉）。
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

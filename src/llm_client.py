"""
LLM API 调用封装
支持 OpenAI 及兼容接口（DeepSeek / 通义千问 / GLM 等）
"""

import os
import json
from openai import OpenAI


class LLMClient:
    """封装 LLM API 调用，兼容所有 OpenAI 格式的接口"""

    def __init__(self):
        # 从环境变量读取配置
        api_key = os.getenv("OPENAI_API_KEY", "sk-your-api-key-here")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def chat(self, system_prompt: str, user_input: str, temperature: float = 0.3) -> str:
        """
        发送对话请求
        Args:
            system_prompt: 系统提示词（定义AI的角色和行为）
            user_input: 用户输入（具体要分析的内容）
            temperature: 随机性，测试场景建议低一些（0.1-0.3）
        Returns:
            LLM 的回复文本
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input},
                ],
                temperature=temperature,
                max_tokens=2000,
            )
            return response.choices[0].message.content
        except Exception as e:
            return json.dumps({
                "error": str(e),
                "verdict": "uncertain",
                "confidence": 0.0,
                "summary": f"LLM 调用失败: {str(e)}",
            }, ensure_ascii=False)

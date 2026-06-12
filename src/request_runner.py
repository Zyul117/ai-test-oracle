"""
请求执行器
发送 HTTP 请求并收集响应
"""

import time
import json
import requests
from dataclasses import dataclass, field


@dataclass
class TestResult:
    """单次测试的执行结果"""
    test_name: str
    method: str
    url: str
    request_params: dict
    request_body: dict
    request_headers: dict

    # 响应
    status_code: int = None
    response_body: dict = None
    response_headers: dict = field(default_factory=dict)
    response_time_ms: float = 0.0

    # 执行状态
    error: str = None  # 网络错误等


class RequestRunner:
    """HTTP 请求执行器"""

    def __init__(self, base_url: str, timeout: int = 15):
        """
        Args:
            base_url: API 的基础地址，如 http://localhost:8080
            timeout: 请求超时秒数
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def run(self, test_case: dict) -> TestResult:
        """
        执行一个测试用例
        Args:
            test_case: 包含 method, path, params, headers, body 的字典
        Returns:
            TestResult 对象
        """
        method = test_case.get("method", "GET").upper()
        path = test_case.get("path", "/")
        url = f"{self.base_url}{path}"
        headers = test_case.get("headers", {})
        params = test_case.get("params", {})
        body = test_case.get("body")

        result = TestResult(
            test_name=test_case.get("test_name", "未命名用例"),
            method=method,
            url=url,
            request_params=params,
            request_body=body,
            request_headers={k: v for k, v in headers.items() if k.lower() != "authorization"},
        )

        start_time = time.time()

        try:
            resp = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=body,
                timeout=self.timeout,
            )

            result.response_time_ms = round((time.time() - start_time) * 1000)
            result.status_code = resp.status_code
            result.response_headers = dict(resp.headers)

            # 尝试解析 JSON 响应
            try:
                result.response_body = resp.json()
            except (json.JSONDecodeError, ValueError):
                result.response_body = {"_raw_text": resp.text[:1000]}

        except requests.exceptions.Timeout:
            result.response_time_ms = round((time.time() - start_time) * 1000)
            result.error = f"请求超时（>{self.timeout}s）"
        except requests.exceptions.ConnectionError as e:
            result.response_time_ms = round((time.time() - start_time) * 1000)
            result.error = f"连接失败: {str(e)[:200]}"
        except requests.exceptions.RequestException as e:
            result.response_time_ms = round((time.time() - start_time) * 1000)
            result.error = f"请求异常: {str(e)[:200]}"

        return result

"""
HTTP 请求执行器

发请求并收集响应，网络异常不抛出而是记在结果里 —— 一条用例连不上
不应该中断整轮测试。
"""

import time
from dataclasses import dataclass, field

import requests


@dataclass
class TestResult:
    """单次请求的执行结果"""

    test_name: str
    method: str
    url: str
    request_params: dict = field(default_factory=dict)
    request_body: dict = None
    request_headers: dict = field(default_factory=dict)

    status_code: int = None
    response_body: object = None
    response_headers: dict = field(default_factory=dict)
    response_time_ms: float = 0.0

    error: str = None      # 网络错误 / 超时等

    @property
    def ok(self) -> bool:
        """请求本身是否发出去并拿到响应（不代表业务判定通过）"""
        return self.error is None and self.status_code is not None


class RequestRunner:
    """HTTP 请求执行器"""

    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout

    def run(self, test_case: dict) -> TestResult:
        """
        执行一个测试用例。
        test_case: {test_name, method, path, params, headers, body}
        """
        method = test_case.get("method", "GET").upper()
        path = test_case.get("path", "/")
        headers = test_case.get("headers") or {}
        params = test_case.get("params") or {}
        body = test_case.get("body")

        result = TestResult(
            test_name=test_case.get("test_name", "未命名用例"),
            method=method,
            url=f"{self.base_url}{path}",
            request_params=params,
            request_body=body,
            # 不把 Authorization 记进结果，避免报告里泄露凭据
            request_headers={k: v for k, v in headers.items()
                             if k.lower() != "authorization"},
        )

        start = time.time()
        try:
            resp = requests.request(
                method=method,
                url=result.url,
                headers=headers,
                params=params,
                json=body,
                timeout=self.timeout,
            )
            result.response_time_ms = round((time.time() - start) * 1000)
            result.status_code = resp.status_code
            result.response_headers = dict(resp.headers)

            try:
                result.response_body = resp.json()
            except ValueError:
                # 非 JSON 响应也要留下来，供 LLM 判断
                result.response_body = resp.text[:2000]

        except requests.exceptions.Timeout:
            result.response_time_ms = round((time.time() - start) * 1000)
            result.error = f"请求超时（>{self.timeout}s）"
        except requests.exceptions.ConnectionError as e:
            result.response_time_ms = round((time.time() - start) * 1000)
            result.error = f"连接失败: {e}"
        except requests.exceptions.RequestException as e:
            result.response_time_ms = round((time.time() - start) * 1000)
            result.error = f"请求异常: {e}"

        return result

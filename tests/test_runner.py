"""
HTTP 执行层测试 —— 打本地 mock server，不需要 API Key

顺带验证 mock server 里那些「状态码 200 但数据有问题」的接口
确实能被 Layer 1 抓到 —— 这是整个项目的立论前提。
"""

import pytest

from ai_oracle import FAIL, PASS, RequestRunner, SchemaValidator


class TestRequestRunner:

    def test_get_success(self, mock_server):
        r = RequestRunner(mock_server).run(
            {"test_name": "查询用户", "method": "GET", "path": "/api/user/1"}
        )
        assert r.ok
        assert r.status_code == 200
        assert r.response_body["user_id"] == 1
        assert r.response_time_ms >= 0

    def test_post_with_body(self, mock_server):
        r = RequestRunner(mock_server).run({
            "test_name": "登录", "method": "POST", "path": "/api/login",
            "body": {"username": "admin", "password": "123456"},
        })
        assert r.status_code == 200
        assert "token" in r.response_body

    def test_query_params(self, mock_server):
        r = RequestRunner(mock_server).run({
            "test_name": "分页", "method": "GET", "path": "/api/product/page",
            "params": {"page": -1},
        })
        assert r.status_code == 200
        assert r.response_body["page"] == -1     # 负页码未校验，返回照样 200

    def test_404_is_not_an_error(self, mock_server):
        """4xx 是正常响应，不算执行失败"""
        r = RequestRunner(mock_server).run(
            {"test_name": "不存在的用户", "method": "GET", "path": "/api/user/999"}
        )
        assert r.ok
        assert r.status_code == 404

    def test_authorization_header_not_recorded(self, mock_server):
        """凭据不能进结果对象，否则会被写进报告"""
        r = RequestRunner(mock_server).run({
            "test_name": "带 token", "method": "GET", "path": "/api/user/1",
            "headers": {"Authorization": "Bearer secret-token", "X-Trace": "abc"},
        })
        assert "Authorization" not in r.request_headers
        assert r.request_headers.get("X-Trace") == "abc"

    def test_connection_error_recorded_not_raised(self):
        """连不上要记进 error 字段，不能抛异常中断整轮"""
        r = RequestRunner("http://127.0.0.1:1", timeout=2).run(
            {"test_name": "连不上", "method": "GET", "path": "/x"}
        )
        assert not r.ok
        assert r.error is not None
        assert r.status_code is None


class TestMockDataIsJudgeable:
    """验证 mock 数据里的隐性 Bug 能被 Layer 1 抓到（不调 LLM）"""

    def setup_method(self):
        self.sv = SchemaValidator()

    @pytest.mark.parametrize("path,reason", [
        ("/api/user/2", "余额为负"),
        ("/api/user/4", "name 为 null"),
        ("/api/product/list", "total 25 但 items 为空"),
    ])
    def test_layer1_catches_bad_data(self, mock_server, path, reason):
        r = RequestRunner(mock_server).run({"test_name": reason, "path": path})
        assert r.status_code == 200, "状态码是 200，传统断言查不出问题"
        assert self.sv.validate(r.response_body).verdict == FAIL, \
            f"Layer 1 应该抓到：{reason}"

    @pytest.mark.parametrize("path", ["/api/user/1", "/api/order/1001"])
    def test_layer1_passes_good_data(self, mock_server, path):
        r = RequestRunner(mock_server).run({"test_name": "正常数据", "path": path})
        assert self.sv.validate(r.response_body).verdict == PASS

    @pytest.mark.parametrize("path,reason", [
        ("/api/user/3", "缺 email 字段"),
        ("/api/order/1002", "total 与明细金额不符"),
        ("/api/order/1003", "已取消却又已发货"),
    ])
    def test_layer1_cannot_catch_semantic_bugs(self, mock_server, path, reason):
        """
        这几条 Layer 1 抓不到 —— 结构完全合法，问题在业务语义。
        正是需要 Layer 2 (LLM) 的场景，也是这个项目存在的理由。
        """
        r = RequestRunner(mock_server).run({"test_name": reason, "path": path})
        assert self.sv.validate(r.response_body).verdict == PASS, \
            f"Layer 1 结构校验挡不住语义问题：{reason}"

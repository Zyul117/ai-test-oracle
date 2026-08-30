"""
本地 Mock API —— 用于演示和跑基准集，不依赖任何外部服务

故意内置了几个「状态码正常但数据有问题」的接口，
这正是传统断言（只查 status_code == 200）覆盖不到、
需要预言机来发现的场景。

启动：python mock_server.py    （默认 http://127.0.0.1:8000）
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

HOST, PORT = "127.0.0.1", 8000


# 路由表：path -> (status_code, response_body)
# 注释里标注这条数据「对不对」，基准集的期望值以此为准
ROUTES = {
    # --- 正常数据 ---
    "/api/user/1": (200, {
        "user_id": 1, "name": "张三",
        "email": "zhangsan@example.com", "balance": 1200.50,
    }),
    "/api/order/1001": (200, {
        "order_id": 1001, "status": "paid",
        "items": [{"sku": "A1", "price": 99.0, "qty": 2}],
        "total": 198.0,          # 与 price*qty 一致
    }),

    # --- 状态码 200 但数据有问题（预言机应该抓到） ---
    "/api/user/2": (200, {
        "user_id": 2, "name": "李四",
        "email": "lisi@example.com", "balance": -500.0,   # 余额为负
    }),
    "/api/user/3": (200, {
        "user_id": 3, "name": "王五",                      # 缺 email
        "balance": 0.0,
    }),
    "/api/user/4": (200, {
        "user_id": 4, "name": None,                        # name 为 null
        "email": "x@example.com", "balance": 100.0,
    }),
    "/api/order/1002": (200, {
        "order_id": 1002, "status": "paid",
        "items": [{"sku": "B2", "price": 50.0, "qty": 3}],
        "total": 100.0,          # 应为 150，金额不自洽
    }),
    "/api/order/1003": (200, {
        "order_id": 1003,
        "status": "shipped",     # 已取消又已发货，状态机矛盾
        "cancelled": True,
        "items": [{"sku": "C3", "price": 20.0, "qty": 1}],
        "total": 20.0,
    }),
    "/api/product/list": (200, {
        "page": 1, "page_size": 10,
        "total": 25,
        "items": [],             # total 25 但列表为空
    }),

    # --- 正常的错误响应 ---
    "/api/user/999": (404, {"error": "user not found", "code": 40401}),
}


# ======================================================================
# 「业务状态码」风格接口族
#
# 取自真实项目的接口约定：HTTP 层恒为 200，真实结果放在 body.status
#   status = 0    成功
#   status = -1   参数校验失败
#   status = 999  会话过期 / 未认证
#
# 这种约定下 `assert status_code == 200` 完全失效 —— 必须读 body 语义，
# 是预言机最典型的适用场景。benchmark/ 下的用例集打的就是这组接口。
#
# 带 `-bug` 后缀的是**故意植入缺陷**的对照接口，用于衡量预言机
# 能不能把「该报错却返回成功」这类问题判出来。
# ======================================================================

def _ok(data=None, **extra):
    return {"status": 0, "message": "success", "data": data if data is not None else {}, **extra}


def _invalid(message, data=None):
    return {"status": -1, "message": message, "data": data or {}}


STATUS_ROUTES = {
    # ---------- 认证 ----------
    # 未带凭据 → 应为 999 会话过期
    ("POST", "/api/notify/unread-count-anon"): lambda body, q: {
        "status": 999, "message": "session expired", "data": {},
    },
    # 带凭据 → status=0
    ("POST", "/api/notify/unread-count"): lambda body, q: _ok({"unread_count": 3}),

    # 空 body 登录 → 应被参数校验拒绝，并报出缺失字段
    ("POST", "/api/auth/login"): lambda body, q: (
        _invalid("数据错误", {"missing": ["Phone", "Validate"]}) if not body.get("Phone")
        else {"status": 2, "message": "验证码错误", "data": {}}
    ),
    # 缺陷对照：空 body 竟然登录成功并下发 token
    ("POST", "/api/auth/login-bug"): lambda body, q: _ok(
        {"token": "eyJhbGciOi.FAKE.TOKEN", "user_id": 1001}
    ),

    # ---------- 用户 ----------
    ("GET", "/api/user/info"): lambda body, q: _ok({
        "user_id": 1001, "nickname": "测试账号", "email": "tester@example.com",
    }),
    ("GET", "/api/user/setting"): lambda body, q: _ok({
        "unit_system": "metric", "language": "zh-CN",
    }),
    # 设置修改后读回：正确实现返回新值
    ("POST", "/api/user/setting"): lambda body, q: _ok({
        "unit_system": body.get("unit_system", "metric"),
        "language": body.get("language", "zh-CN"),
    }),
    # 缺陷对照：提交 imperial/en-US，回显却还是旧值（写入未生效）
    ("POST", "/api/user/setting-bug"): lambda body, q: _ok({
        "unit_system": "metric", "language": "zh-CN",
    }),

    # ---------- 项目 / 任务分页 ----------
    ("POST", "/api/project/list"): lambda body, q: (
        _invalid("Page is required") if not body.get("page")
        else _ok({"list": [{"id": 1, "name": "项目A"}], "total": 1,
                  "page": body.get("page"), "size": body.get("size", 10)})
    ),
    # 缺陷对照：page=0 未被校验，照样返回数据
    ("POST", "/api/project/list-bug"): lambda body, q: _ok({
        "list": [{"id": 1, "name": "项目A"}], "total": 1,
        "page": body.get("page", 0), "size": body.get("size", 10),
    }),
    ("POST", "/api/task/list"): lambda body, q: _ok({
        "list": [{"id": 9, "title": "任务A", "state": "done"}], "total": 1,
        "page": body.get("page", 1), "size": body.get("size", 10),
    }),

    # ---------- 积分 ----------
    ("POST", "/api/credit/balance"): lambda body, q: _ok({
        "balance": 250, "frozen": 0,
    }),
    ("POST", "/api/credit/transactions"): lambda body, q: _ok({
        "list": [{"id": 7, "amount": -10, "balance_after": 250,
                  "created_at": "2026-08-20T10:00:00Z"}],
    }),
    # 缺陷对照：流水缺 balance_after，对不出账
    ("POST", "/api/credit/transactions-bug"): lambda body, q: _ok({
        "list": [{"id": 7, "amount": -10, "created_at": "2026-08-20T10:00:00Z"}],
    }),
    # 签到幂等：已签到时不再发分
    ("POST", "/api/credit/checkin"): lambda body, q: _ok(
        {"granted": False, "amount": 0, "streak": 3}
    ),
    # 缺陷对照：重复签到又发了一次分
    ("POST", "/api/credit/checkin-bug"): lambda body, q: _ok(
        {"granted": True, "amount": 5, "streak": 4}
    ),

    # ---------- 通知 ----------
    ("POST", "/api/notify/read-all"): lambda body, q: _ok({"unread_count": 0}),
    # 缺陷对照：声称已读全部，未读数却没归零
    ("POST", "/api/notify/read-all-bug"): lambda body, q: _ok({"unread_count": 3}),

    # ---------- 公开接口 ----------
    ("POST", "/api/showcase/list"): lambda body, q: _ok({
        "list": [{"id": 1, "title": "案例A", "cover": "/img/a.png"}], "total": 1,
    }),

    # ---------- 固定在这里的是“难判”样本 ----------
    # 用于检验预言机在细微不一致、以及信息不足时的表现。

    # total 声称 99 条，实际 list 只有 1 条（且非最后一页）
    ("POST", "/api/project/list-count-mismatch"): lambda body, q: _ok({
        "list": [{"id": 1, "name": "项目A"}],
        "total": 99, "page": 1, "size": 10,
    }),
    # 积分余额为负
    ("POST", "/api/credit/balance-negative"): lambda body, q: _ok({
        "balance": -50, "frozen": 0,
    }),
    # 流水时间戳是未来时间
    ("POST", "/api/credit/transactions-future"): lambda body, q: _ok({
        "list": [{"id": 8, "amount": -10, "balance_after": 240,
                  "created_at": "2099-01-01T00:00:00Z"}],
    }),
    # 流水前后余额对不上：240 - 10 应为 230，却写了 250
    ("POST", "/api/credit/transactions-math"): lambda body, q: _ok({
        "list": [{"id": 9, "amount": -10,
                  "balance_before": 240, "balance_after": 250}],
    }),
}


class MockHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        handler = STATUS_ROUTES.get(("GET", path))
        if handler:
            self._send(200, handler({}, query))
            return

        # 分页接口：演示参数校验缺失（page=-1 也照样返回 200）
        if path == "/api/product/page":
            page = int(query.get("page", ["1"])[0])
            self._send(200, {
                "page": page,          # 负数页码未做校验
                "page_size": 10,
                "total": 25,
                "items": [{"id": 1, "name": "商品A", "price": 19.9}],
            })
            return

        if path in ROUTES:
            status, body = ROUTES[path]
            self._send(status, body)
            return

        self._send(404, {"error": "not found", "path": path})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        handler = STATUS_ROUTES.get(("POST", path))
        if handler:
            self._send(200, handler(payload, query))
            return

        if path == "/api/login":
            username = payload.get("username", "")
            password = payload.get("password", "")
            # 空用户名也返回 200，这是个真实常见的参数校验缺失
            if not username or not password:
                self._send(200, {"code": 0, "token": "fake-token-empty-user",
                                 "message": "login success"})
            else:
                self._send(200, {"code": 0, "token": "fake-token-abc123",
                                 "message": "login success"})
            return

        self._send(404, {"error": "not found", "path": path})

    def _send(self, status: int, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass    # 静音，避免刷屏


def serve(host: str = HOST, port: int = PORT):
    server = HTTPServer((host, port), MockHandler)
    print(f"Mock API 已启动: http://{host}:{port}")
    print("试试: curl http://127.0.0.1:8000/api/user/2   （余额为负，状态码却是 200）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()


if __name__ == "__main__":
    serve()

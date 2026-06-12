"""
第一层：Schema 校验（零成本、零幻觉）
用 jsonschema 库验证 API 返回值的结构是否符合接口文档定义
"""

import jsonschema
from jsonschema import ValidationError


class SchemaValidator:
    """根据 OpenAPI Schema 定义校验响应结构"""

    def validate(self, response_body, response_schema: dict) -> dict:
        """
        校验响应结构
        Args:
            response_body: API 实际返回的 JSON
            response_schema: 接口文档中定义的期望结构
        Returns:
            {"passed": bool, "issues": list[str]}
        """
        issues = []

        if not response_schema:
            return {"passed": True, "issues": [], "note": "未提供 Schema 定义，跳过结构校验"}

        try:
            jsonschema.validate(instance=response_body, schema=response_schema)
        except ValidationError as e:
            # 把 jsonschema 的技术错误信息翻译成人话
            path = " → ".join(str(p) for p in e.absolute_path) if e.absolute_path else "根对象"
            issues.append(f"字段 [{path}] 校验失败: {e.message}")

        # 额外检查：常见的问题模式
        self._extra_checks(response_body, issues)

        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }

    def _extra_checks(self, response_body, issues: list):
        """额外的常见问题检查（不依赖Schema），支持 dict 和 list 类型"""
        # 如果响应是数组，逐个检查数组中的每个元素
        if isinstance(response_body, list):
            if len(response_body) == 0:
                issues.append("返回了空数组，可能数据缺失或查询条件有误")
            for i, item in enumerate(response_body):
                if isinstance(item, dict):
                    self._check_dict_fields(item, issues, prefix=f"数组第{i}项")
            return

        # 如果响应是字典
        if isinstance(response_body, dict):
            self._check_dict_fields(response_body, issues, prefix="")

    def _check_dict_fields(self, data: dict, issues: list, prefix: str = ""):
        """检查字典字段的常见问题"""
        name_prefix = f"{prefix}的字段 " if prefix else "字段 '"
        name_suffix = "'" if not prefix else ""

        for key, value in data.items():
            full_name = f"{name_prefix}{key}{name_suffix}"

            if value is None:
                issues.append(f"{full_name} 的值为 null，可能是数据缺失")

            # 检查负数金额
            if key.lower() in ("price", "amount", "total", "balance", "cost", "fee"):
                if isinstance(value, (int, float)) and value < 0:
                    issues.append(f"{full_name} 为负数 ({value})，可能异常")

            # 检查空列表
            if isinstance(value, list) and len(value) == 0:
                if key.lower() in ("items", "data", "results", "records", "list"):
                    issues.append(f"{full_name} 为空，可能数据缺失或查询条件有误")

    def build_schema_from_openapi(self, openapi_spec: dict, path: str, method: str) -> dict:
        """
        从 OpenAPI 3.0 规范中提取某个接口的响应 Schema
        Args:
            openapi_spec: 完整的 OpenAPI JSON
            path: 接口路径，如 "/api/users"
            method: HTTP 方法，如 "get"
        Returns:
            该接口 200 响应的 Schema，如果找不到则返回空 dict
        """
        try:
            return (
                openapi_spec.get("paths", {})
                .get(path, {})
                .get(method.lower(), {})
                .get("responses", {})
                .get("200", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
            )
        except Exception:
            return {}

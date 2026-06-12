"""
测试输入生成器
基于经典的测试方法生成参数组合：边界值、等价类、异常值
"""

import copy


class InputGenerator:
    """根据接口参数定义，自动生成测试输入"""

    def generate(self, params_definition: list[dict], base_request: dict) -> list[dict]:
        """
        生成测试用例列表
        Args:
            params_definition: 参数定义列表，每个元素有 name, type, constraints
                例如: [{"name": "page", "type": "integer", "min": 1, "max": 100}]
            base_request: 基础请求模板 {"method": "GET", "path": "/api/users", "headers": {}, "params": {}}
        Returns:
            测试用例列表，每个用例包含完整的请求信息
        """
        all_cases = []

        # 先生成一个"正常"用例作为基准
        normal_case = copy.deepcopy(base_request)
        normal_case["test_name"] = "【基准用例】正常参数"
        normal_case["test_strategy"] = "正常值"
        all_cases.append(normal_case)

        # 对每个参数，生成边界值和异常值用例
        for param in params_definition:
            param_name = param.get("name", "unknown")
            param_type = param.get("type", "string")
            param_location = param.get("in", "query")  # query / body / path

            # 根据类型生成不同的测试值
            test_values = self._generate_values(param)

            for test_val, strategy in test_values:
                case = copy.deepcopy(base_request)
                case["test_name"] = f"【{strategy}】{param_name} = {test_val}"
                case["test_strategy"] = strategy

                # 把测试值放到正确的位置
                if param_location == "query" or param_location == "path":
                    case.setdefault("params", {})
                    case["params"][param_name] = test_val
                elif param_location == "body":
                    case.setdefault("body", {})
                    case["body"][param_name] = test_val
                elif param_location == "header":
                    case.setdefault("headers", {})
                    case["headers"][param_name] = str(test_val)

                all_cases.append(case)

        return all_cases

    def _generate_values(self, param: dict) -> list[tuple]:
        """
        根据参数类型生成测试值列表
        返回: [(值, 策略名称), ...]
        """
        param_type = param.get("type", "string")
        values = []

        if param_type in ("integer", "number"):
            minimum = param.get("minimum")
            maximum = param.get("maximum")

            if minimum is not None and maximum is not None:
                # 边界值分析
                values.append((minimum - 1, "边界值（最小值-1）"))
                values.append((minimum, "边界值（最小值）"))
                values.append((minimum + 1, "边界值（最小值+1）"))
                values.append((maximum - 1, "边界值（最大值-1）"))
                values.append((maximum, "边界值（最大值）"))
                values.append((maximum + 1, "边界值（最大值+1）"))
            elif minimum is not None:
                values.append((minimum - 1, "边界值（最小值-1）"))
                values.append((minimum, "边界值（最小值）"))
                values.append((minimum + 1, "边界值（最小值+1）"))

            # 特殊值
            values.append((0, "特殊值（0）"))
            values.append((-1, "异常值（负数）"))

        elif param_type == "string":
            min_len = param.get("minLength", 0)
            max_len = param.get("maxLength", 255)

            # 枚举类型
            if "enum" in param:
                for val in param["enum"]:
                    values.append((val, "合法枚举值"))
                values.append(("INVALID_VALUE_XYZ", "非法枚举值"))
            else:
                values.append(("", "边界值（空字符串）"))
                values.append(("A" * (max_len + 1), f"边界值（超长>{max_len}）"))
                values.append(("<script>alert(1)</script>", "安全测试（XSS）"))
                values.append(("' OR '1'='1", "安全测试（SQL注入）"))
                values.append(("你好世界", "Unicode测试"))

        elif param_type == "boolean":
            values.append((True, "true值"))
            values.append((False, "false值"))
            values.append(("true", "异常值（字符串'true'）"))
            values.append((1, "异常值（数字1）"))

        elif param_type == "array":
            values.append(([], "边界值（空数组）"))
            values.append(([None], "异常值（含null的数组）"))

        return values

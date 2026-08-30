"""
报告生成

合并前 report.py 是靠 final_verdict 字符串 startswith("PASS") 来分类的，
改成直接读 Verdict.verdict 枚举值，不再依赖文案格式。
"""

from datetime import datetime

from .verdict import FAIL, PASS, UNCERTAIN


class ReportGenerator:
    """把每条用例的判定结果汇总成统计数据和文本报告"""

    def summarize(self, results: list[dict]) -> dict:
        """
        results: [{"test_name": str, "verdict": Verdict, ...}, ...]
        """
        total = len(results)
        if total == 0:
            return {"total": 0, "message": "没有测试结果"}

        counts = {PASS: 0, FAIL: 0, UNCERTAIN: 0}
        failures = []

        for item in results:
            verdict = item.get("verdict")
            key = getattr(verdict, "verdict", UNCERTAIN)
            counts[key] = counts.get(key, 0) + 1

            if key == FAIL:
                failures.append({
                    "test_name": item.get("test_name", ""),
                    "reason": getattr(verdict, "reason", ""),
                    "confidence": getattr(verdict, "confidence", 0.0),
                    "issues": getattr(verdict, "detail", {}).get("issues", []),
                })

        return {
            "total": total,
            "pass": counts[PASS],
            "fail": counts[FAIL],
            "uncertain": counts[UNCERTAIN],
            "pass_rate": f"{counts[PASS] / total * 100:.1f}%",
            "failures": failures,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def to_text(self, summary: dict) -> str:
        """生成可直接贴进报告的纯文本"""
        if summary.get("total", 0) == 0:
            return "没有测试结果"

        sep = "=" * 52
        lines = [
            sep,
            "        AI Test Oracle — 测试报告",
            sep,
            f"生成时间: {summary['generated_at']}",
            f"总用例数 : {summary['total']}",
            f"通过     : {summary['pass']}",
            f"失败     : {summary['fail']}",
            f"不确定   : {summary['uncertain']}",
            f"通过率   : {summary['pass_rate']}",
            "",
        ]

        if summary.get("failures"):
            lines += ["-" * 52, "  疑似 Bug 详情", "-" * 52]
            for i, f in enumerate(summary["failures"], 1):
                lines.append(f"\n[{i}] {f['test_name']}")
                lines.append(f"    置信度: {f['confidence']:.0%}")
                lines.append(f"    判断依据: {f['reason']}")
                for issue in f.get("issues", [])[:5]:
                    lines.append(f"      - {issue}")

        lines += ["", sep]
        return "\n".join(lines)

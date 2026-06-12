"""
报告生成器
将测试结果汇总成可读的文本和结构化数据
"""

from datetime import datetime


class ReportGenerator:
    """生成测试汇总报告"""

    def generate_summary(self, all_results: list[dict]) -> dict:
        """
        生成汇总统计
        Args:
            all_results: 每个测试用例的完整判断结果列表
        Returns:
            汇总数据
        """
        total = len(all_results)
        if total == 0:
            return {"total": 0, "message": "没有测试结果"}

        pass_count = 0
        fail_count = 0
        uncertain_count = 0
        errors = []

        for r in all_results:
            verdict = r.get("final_verdict", "")
            if verdict.startswith("PASS"):
                pass_count += 1
            elif verdict.startswith("FAIL"):
                fail_count += 1
                errors.append({
                    "test_name": r.get("test_name", ""),
                    "verdict": verdict,
                    "findings": r.get("findings_detail", []),
                })
            else:
                uncertain_count += 1

        return {
            "total": total,
            "pass": pass_count,
            "fail": fail_count,
            "uncertain": uncertain_count,
            "pass_rate": f"{pass_count / total * 100:.1f}%" if total > 0 else "N/A",
            "errors": errors,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def generate_text_report(self, summary: dict) -> str:
        """生成人类可读的文本报告"""
        lines = []
        lines.append("=" * 50)
        lines.append("       AI Test Oracle — 测试报告")
        lines.append("=" * 50)
        lines.append(f"生成时间: {summary.get('generated_at', '')}")
        lines.append(f"总测试数: {summary.get('total', 0)}")
        lines.append(f"✅ 通过: {summary.get('pass', 0)}")
        lines.append(f"❌ 失败: {summary.get('fail', 0)}")
        lines.append(f"❓ 不确定: {summary.get('uncertain', 0)}")
        lines.append(f"通过率: {summary.get('pass_rate', 'N/A')}")
        lines.append("")

        if summary.get("errors"):
            lines.append("-" * 50)
            lines.append("  疑似 Bug 详情")
            lines.append("-" * 50)
            for i, err in enumerate(summary["errors"], 1):
                lines.append(f"\n[{i}] {err.get('test_name', '')}")
                lines.append(f"    判断: {err.get('verdict', '')}")
                for finding in err.get("findings", []):
                    lines.append(f"    来源: {finding.get('layer', '')}")
                    lines.append(f"    详情: {str(finding.get('detail', ''))[:200]}")

        lines.append("")
        lines.append("=" * 50)
        lines.append("  报告结束 — AI Test Oracle")
        lines.append("=" * 50)

        return "\n".join(lines)

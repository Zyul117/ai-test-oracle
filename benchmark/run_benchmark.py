"""
基准集运行器 —— 衡量 LLM 语义判定的准确率

用人工标注了 ground truth 的用例集跑一遍预言机，统计：
  - 准确率：判定与标注一致的比例
  - 漏报：该报 fail 却判了 pass（测试工具最危险的错误）
  - 误报：该判 pass 却报了 fail（会浪费排查时间）
  - 不确定：判了 uncertain，交人工复核

先起 mock server：
    python mock_server.py

再跑：
    python benchmark/run_benchmark.py
    python benchmark/run_benchmark.py --cases benchmark/cases.example.yaml
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_oracle import FAIL, PASS, UNCERTAIN, LLMOracle, RequestRunner, has_api_key  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
DEFAULT_CASES = Path(__file__).parent / "cases.yaml"


def load_cases(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"用例文件不存在: {path}")
    cases = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not cases:
        sys.exit(f"用例文件为空: {path}")
    return cases


def run(cases: list[dict], base_url: str) -> list[dict]:
    runner = RequestRunner(base_url)
    oracle = LLMOracle()
    records = []

    for i, case in enumerate(cases, 1):
        cid = case.get("id", f"#{i}")
        title = case.get("title", "")
        expected = case.get("expected_verdict", PASS)

        resp = runner.run({
            "test_name": title,
            "method": case.get("method", "POST"),
            "path": case["path"],
            "body": case.get("body"),
        })

        if not resp.ok:
            print(f"[{cid}] 请求失败: {resp.error}")
            print("      请先运行 python mock_server.py")
            sys.exit(1)

        t0 = time.time()
        verdict = oracle.judge_expectation(resp.response_body, case["expectation"])
        elapsed = time.time() - t0

        correct = verdict.verdict == expected
        mark = "OK " if correct else ("?? " if verdict.verdict == UNCERTAIN else "XX ")

        print(f"{mark}[{cid}] {title}")
        print(f"       标注={expected:9s} 判定={verdict.verdict:9s} "
              f"置信度={verdict.confidence:.0%}  {elapsed:.1f}s")
        if not correct:
            print(f"       LLM 依据: {verdict.reason}")

        records.append({
            "id": cid, "title": title, "module": case.get("module", ""),
            "priority": case.get("priority", ""),
            "expected": expected, "actual": verdict.verdict,
            "confidence": verdict.confidence, "reason": verdict.reason,
            "correct": correct, "elapsed": round(elapsed, 2),
            "http_status": resp.status_code,
        })

    return records


def report(records: list[dict]) -> dict:
    total = len(records)
    correct = sum(1 for r in records if r["correct"])
    uncertain = sum(1 for r in records if r["actual"] == UNCERTAIN)

    # 漏报：该 fail 却判 pass —— 缺陷被放过，最危险
    missed = [r for r in records if r["expected"] == FAIL and r["actual"] == PASS]
    # 误报：该 pass 却判 fail —— 制造无效排查
    false_alarm = [r for r in records if r["expected"] == PASS and r["actual"] == FAIL]

    sep = "=" * 64
    print(f"\n{sep}")
    print("  基准集结果")
    print(sep)
    print(f"  用例总数   : {total}")
    print(f"  判定正确   : {correct}")
    print(f"  准确率     : {correct / total * 100:.1f}%")
    print(f"  漏报       : {len(missed)}  （该报 fail 却判 pass）")
    print(f"  误报       : {len(false_alarm)}  （该判 pass 却报 fail）")
    print(f"  不确定     : {uncertain}  （交人工复核）")
    print(f"  平均耗时   : {sum(r['elapsed'] for r in records) / total:.1f}s / 条")

    for label, group in (("漏报明细", missed), ("误报明细", false_alarm)):
        if group:
            print(f"\n  {label}")
            for r in group:
                print(f"    [{r['id']}] {r['title']}")
                print(f"          {r['reason']}")

    by_module = Counter(r["module"] for r in records)
    ok_by_module = Counter(r["module"] for r in records if r["correct"])
    print("\n  分模块准确率")
    for mod, n in sorted(by_module.items()):
        print(f"    {mod or '(未分类)':6s} {ok_by_module[mod]}/{n}")

    print(sep)

    return {
        "total": total, "correct": correct,
        "accuracy": round(correct / total, 4),
        "missed": len(missed), "false_alarm": len(false_alarm),
        "uncertain": uncertain,
    }


def main():
    ap = argparse.ArgumentParser(description="基准集运行器")
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--out", type=Path, default=None,
                    help="把逐条结果写成 JSON（默认不写）")
    args = ap.parse_args()

    if not has_api_key():
        sys.exit("需要配置 OPENAI_API_KEY 才能跑基准集（基准集衡量的就是 LLM 判定准确率）")

    cases = load_cases(args.cases)
    print(f"用例集: {args.cases}  共 {len(cases)} 条\n")

    records = run(cases, args.base_url)
    summary = report(records)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"summary": summary, "records": records},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n逐条结果已写入 {args.out}")


if __name__ == "__main__":
    main()

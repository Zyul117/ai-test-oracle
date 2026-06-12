# -*- coding: utf-8 -*-
"""
Command-line demo script
Usage: python demo.py
Requires: OPENAI_API_KEY env variable set
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.llm_client import LLMClient
from src.llm_oracle import LLMOracle


def main():
    print("=" * 60)
    print("  AI Test Oracle - Command Line Demo")
    print("=" * 60)

    # Mock scenario: user info API
    api_spec = """
API: Get user info
Path: GET /api/users/{id}
Returns: id, name, email, age, balance
Rules:
  - age should >= 0
  - balance should not be negative
  - email should be valid
  - name should not be empty
"""

    request_info = {
        "method": "GET",
        "path": "/api/users/42",
        "params": {},
        "body": None,
    }

    # Response with a bug: negative balance
    bad_response = {
        "id": 42,
        "name": "Zhang San",
        "email": "zhangsan@example.com",
        "age": 25,
        "balance": -500.00,  # <-- BUG! balance should not be negative
    }

    # Init Oracle
    print("\n[1/2] Initializing LLM Oracle...")
    try:
        llm = LLMClient()
        oracle = LLMOracle(llm)
        print("  [OK] LLM client ready")
        print(f"  Model: {llm.model}")
        print(f"  Base URL: {llm.client.base_url}")
    except Exception as e:
        print(f"  [FAIL] Init failed: {e}")
        print("  Hint: please set OPENAI_API_KEY env variable")
        return

    # Test: bad response
    print("\n[2/2] Testing: response with negative balance")

    print(f"\n  Response: {json.dumps(bad_response, ensure_ascii=False)}")
    print(f"  Expected: Oracle should detect negative balance as a bug")

    result = oracle.judge(api_spec, request_info, bad_response, 200)

    print(f"\n  Oracle Result:")
    print(f"     Verdict: {result.get('verdict', '?')}")
    print(f"     Confidence: {result.get('confidence', 0):.0%}")
    print(f"     Summary: {result.get('summary', '?')}")

    if result.get("step1_data_check"):
        s1 = result["step1_data_check"]
        status = "PASS" if s1.get('passed') else "FAIL"
        print(f"     Step1 Data Check: {status}")
        if s1.get("issues"):
            for issue in s1["issues"]:
                print(f"       - {issue}")

    if result.get("step2_logic_check"):
        s2 = result["step2_logic_check"]
        status = "PASS" if s2.get('passed') else "FAIL"
        print(f"     Step2 Logic Check: {status}")
        if s2.get("issues"):
            for issue in s2["issues"]:
                print(f"       - {issue}")

    if result.get("bug_hypothesis"):
        print(f"     Bug Hypothesis: {result['bug_hypothesis']}")

    print("\n" + "=" * 60)
    print("  Demo Complete!")
    print("  Oracle found hidden bugs without manual assertions")
    print("=" * 60)


if __name__ == "__main__":
    main()

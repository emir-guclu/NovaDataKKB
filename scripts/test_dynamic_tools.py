from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Ensure UTF-8 output encoding on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from backend.app.agent.loop import run_agent
from backend.app.agent.tool_registry import ToolRegistry
from backend.app.core.llm_provider import KloudeksProvider
from backend.app.tools.anomaly_detection import AnomalyDetectionTool
from backend.app.tools.causality_check import CausalityCheckTool
from backend.app.tools.change_detection import ChangeDetectionTool
from backend.app.tools.lakehouse_query import LakehouseQueryTool
from backend.app.tools.web_search import WebSearchTool

logger = logging.getLogger("test_dynamic_tools")

# 10 Prompts across 5 dynamic tools as defined in the plan
TEST_SCENARIOS = [
    # 1. ChangeDetectionTool
    {
        "id": "1.1",
        "tool_class": "ChangeDetectionTool",
        "expected_tool": "change_detection",
        "prompt": "Konut kredileri hacmi geçen aya göre nasıl ve ne kadar değişti?",
    },
    {
        "id": "1.2",
        "tool_class": "ChangeDetectionTool",
        "expected_tool": "change_detection",
        "prompt": "Taşıt kredisi hacmindeki yıllık değişim yüzdesi nedir?",
    },
    # 2. WebSearchTool
    {
        "id": "2.1",
        "tool_class": "WebSearchTool",
        "expected_tool": "web_search",
        "prompt": "Türkiye'nin 2026 yılı güncel enflasyon oranı ve TÜİK son haberleri nelerdir?",
    },
    {
        "id": "2.2",
        "tool_class": "WebSearchTool",
        "expected_tool": "web_search",
        "prompt": "TCMB'nin en son faiz kararı ve açıklamaları nelerdir?",
    },
    # 3. LakehouseQueryTool
    {
        "id": "3.1",
        "tool_class": "LakehouseQueryTool",
        "expected_tool": "lakehouse_query",
        "prompt": "2021 yılı konut kredisi faiz oranlarını Lakehouse veritabanından getir.",
    },
    {
        "id": "3.2",
        "tool_class": "LakehouseQueryTool",
        "expected_tool": "lakehouse_query",
        "prompt": "Gold katmanındaki konut piyasası tablosunun tarih ve faiz oranı verilerini sorgula.",
    },
    # 4. CausalityCheckTool
    {
        "id": "4.1",
        "tool_class": "CausalityCheckTool",
        "expected_tool": "causality_check",
        "prompt": "Konut kredileri ile taşıt kredileri arasında istatistiksel bir korelasyon var mı?",
    },
    {
        "id": "4.2",
        "tool_class": "CausalityCheckTool",
        "expected_tool": "causality_check",
        "prompt": "Tüketici kredileri ile konut kredilerinin değişimi birbiriyle ilişkili mi?",
    },
    # 5. AnomalyDetectionTool
    {
        "id": "5.1",
        "tool_class": "AnomalyDetectionTool",
        "expected_tool": "anomaly_detection",
        "prompt": "Konut kredisi hacminde son dönemde olağan dışı bir sıçrama veya anomali var mı?",
    },
    {
        "id": "5.2",
        "tool_class": "AnomalyDetectionTool",
        "expected_tool": "anomaly_detection",
        "prompt": "Taşıt kredisi değişimlerinde z-score bazında anomali tespit et.",
    },
]


@dataclass
class StepTiming:
    iteration: int
    step_type: str  # "llm_decision", "tool_output", "llm_final"
    name: str
    duration_s: float


@dataclass
class TestCaseResult:
    scenario_id: str
    tool_class: str
    expected_tool: str
    prompt: str
    selected_tools: list[str] = field(default_factory=list)
    tool_success: bool = False
    passed: bool = False
    duration_s: float = 0.0
    llm_time_s: float = 0.0
    tool_time_s: float = 0.0
    step_timings: list[dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""
    error: str | None = None


def create_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ChangeDetectionTool())
    registry.register(WebSearchTool())
    registry.register(LakehouseQueryTool())
    registry.register(CausalityCheckTool())
    registry.register(AnomalyDetectionTool())
    return registry


def run_single_test(scenario: dict[str, str], registry: ToolRegistry, provider: KloudeksProvider) -> TestCaseResult:
    scenario_id = scenario["id"]
    tool_class = scenario["tool_class"]
    expected_tool = scenario["expected_tool"]
    prompt = scenario["prompt"]

    print("\n" + "=" * 90)
    print(f" TEST {scenario_id} [{tool_class}] -> Expected Tool: '{expected_tool}'")
    print("=" * 90)

    selected_tools: list[str] = []
    tool_success = False
    step_timings: list[StepTiming] = []
    recorded_llm_calls: set[int] = set()

    def on_event(event_type: str, data: dict[str, Any]) -> None:
        nonlocal tool_success
        iteration = data.get("iteration", 1)

        if event_type == "llm_input":
            if iteration == 1:
                print("\n[LLM INPUT]")
                print(f"User Prompt: {prompt}")
            else:
                print(f"\n[LLM INPUT - Iteration {iteration}]")
                last_msg = data.get("messages", [])[-1] if data.get("messages") else {}
                print(f"Last Role in Context: {last_msg.get('role')}")

        elif event_type == "llm_decision":
            tool_name = data.get("tool_name", "")
            arguments = data.get("arguments", "{}")
            llm_duration_s = data.get("llm_duration_s", 0.0)
            selected_tools.append(tool_name)

            if iteration not in recorded_llm_calls:
                recorded_llm_calls.add(iteration)
                step_timings.append(
                    StepTiming(
                        iteration=iteration,
                        step_type="llm_decision",
                        name=f"LLM Call (Iter {iteration})",
                        duration_s=llm_duration_s,
                    )
                )

            print(f"\n[LLM DECISION] (LLM Response Time: {llm_duration_s:.2f}s)")
            print(f"Selected Tool: {tool_name}")
            try:
                args_dict = json.loads(arguments)
                print(f"Parameters: {json.dumps(args_dict, ensure_ascii=False, indent=2)}")
            except Exception:
                print(f"Parameters (raw): {arguments}")

        elif event_type == "tool_output":
            tool_name = data.get("tool_name", "")
            raw_result = data.get("result", "")
            success = data.get("success", False)
            tool_duration_s = data.get("tool_duration_s", 0.0)
            if success:
                tool_success = True

            step_timings.append(
                StepTiming(
                    iteration=iteration,
                    step_type="tool_output",
                    name=tool_name,
                    duration_s=tool_duration_s,
                )
            )

            print(f"\n[TOOL OUTPUT] (Tool: {tool_name} | Success: {success} | Exec Time: {tool_duration_s:.3f}s)")
            if len(raw_result) > 600:
                print(f"Result (truncated): {raw_result[:600]}... [total {len(raw_result)} chars]")
            else:
                print(f"Result: {raw_result}")

        elif event_type == "llm_input_after_tool":
            content = data.get("content", "")
            print("\n[LLM INPUT AFTER TOOL]")
            if len(content) > 300:
                print(f"Payload fed to LLM: {content[:300]}... [total {len(content)} chars]")
            else:
                print(f"Payload fed to LLM: {content}")

        elif event_type == "llm_final":
            answer = data.get("answer", "")
            llm_duration_s = data.get("llm_duration_s", 0.0)
            if llm_duration_s > 0:
                step_timings.append(
                    StepTiming(
                        iteration=iteration,
                        step_type="llm_final",
                        name=f"LLM Final Synthesis (Iter {iteration})",
                        duration_s=llm_duration_s,
                    )
                )
            print(f"\n[LLM FINAL] (LLM Response Time: {llm_duration_s:.2f}s)")
            print(f"Answer: {answer.strip()}")

    start_time = time.perf_counter()
    error_str: str | None = None
    final_answer = ""

    try:
        final_answer = run_agent(
            question=prompt,
            registry=registry,
            provider=provider,
            max_iterations=5,
            on_event=on_event,
        )
    except Exception as exc:
        logger.exception("Error executing test %s", scenario_id)
        error_str = str(exc)
        print(f"\n[ERROR]: {exc}")

    total_duration = time.perf_counter() - start_time

    # Calculate timing breakdowns
    llm_total_time = sum(st.duration_s for st in step_timings if "llm" in st.step_type)
    tool_total_time = sum(st.duration_s for st in step_timings if st.step_type == "tool_output")

    print(
        f"\n[TIMING SUMMARY {scenario_id}]: LLM Total: {llm_total_time:.2f}s | "
        f"Tool Total: {tool_total_time:.2f}s | Overall Duration: {total_duration:.2f}s"
    )

    tool_matched = expected_tool in selected_tools
    passed = tool_matched and (error_str is None) and bool(final_answer.strip())

    return TestCaseResult(
        scenario_id=scenario_id,
        tool_class=tool_class,
        expected_tool=expected_tool,
        prompt=prompt,
        selected_tools=selected_tools,
        tool_success=tool_success,
        passed=passed,
        duration_s=total_duration,
        llm_time_s=llm_total_time,
        tool_time_s=tool_total_time,
        step_timings=[asdict(st) for st in step_timings],
        final_answer=final_answer,
        error=error_str,
    )


def print_summary_table(results: list[TestCaseResult]) -> None:
    print("\n" + "=" * 105)
    print("                              COMPREHENSIVE TEST & TIMING REPORT")
    print("=" * 105)
    header = (
        f"{'ID':<5} | {'Target Tool':<20} | {'Expected':<16} | {'Selected':<18} | "
        f"{'Status':<6} | {'LLM Time':<9} | {'Tool Time':<9} | {'Total'}"
    )
    print(header)
    print("-" * 105)

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.passed)
    matched_tools = sum(1 for r in results if r.expected_tool in r.selected_tools)
    total_time = sum(r.duration_s for r in results)
    total_llm_time = sum(r.llm_time_s for r in results)
    total_tool_time = sum(r.tool_time_s for r in results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        selected_str = ", ".join(r.selected_tools) if r.selected_tools else "None"
        if len(selected_str) > 18:
            selected_str = selected_str[:15] + "..."
        print(
            f"{r.scenario_id:<5} | {r.tool_class:<20} | {r.expected_tool:<16} | {selected_str:<18} | "
            f"{status:<6} | {r.llm_time_s:7.2f}s | {r.tool_time_s:7.2f}s | {r.duration_s:6.2f}s"
        )

    print("-" * 105)
    print(f"Total Tests Executed   : {total_tests}")
    print(f"Passed Tests           : {passed_tests}/{total_tests} ({passed_tests / total_tests * 100:.1f}%)")
    print(f"Tool Choice Accuracy   : {matched_tools}/{total_tests} ({matched_tools / total_tests * 100:.1f}%)")
    print(f"Cumulative LLM Time    : {total_llm_time:.2f}s (Average: {total_llm_time / total_tests:.2f}s per test)")
    print(f"Cumulative Tool Time   : {total_tool_time:.2f}s (Average: {total_tool_time / total_tests:.2f}s per test)")
    print(f"Total Test Duration    : {total_time:.2f}s (Average: {total_time / total_tests:.2f}s per test)")
    print("=" * 105)


def save_json_report(results: list[TestCaseResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_tests": len(results),
        "passed_tests": sum(1 for r in results if r.passed),
        "tool_accuracy_pct": (sum(1 for r in results if r.expected_tool in r.selected_tools) / len(results)) * 100,
        "cumulative_llm_time_s": sum(r.llm_time_s for r in results),
        "cumulative_tool_time_s": sum(r.tool_time_s for r in results),
        "total_duration_s": sum(r.duration_s for r in results),
        "test_cases": [asdict(r) for r in results],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"\n[REPORT SAVED] Detailed timing and execution metrics saved to: {output_path}")


def main() -> None:
    load_dotenv()

    if not os.getenv("MIA_API_KEY"):
        print("[ERROR] MIA_API_KEY is not set in environment or .env file.")
        sys.exit(1)

    print("Initializing KloudeksProvider and registering 5 Dynamic Tools...")
    registry = create_registry()
    provider = KloudeksProvider()

    results: list[TestCaseResult] = []

    scenarios = TEST_SCENARIOS
    if len(sys.argv) > 1:
        filters = [arg.lower() for arg in sys.argv[1:]]
        scenarios = [
            s for s in TEST_SCENARIOS
            if s["id"] in filters or s["expected_tool"].lower() in filters or s["tool_class"].lower() in filters
        ]
        if not scenarios:
            print(f"[WARN] No scenarios matched filters: {sys.argv[1:]}. Running all.")
            scenarios = TEST_SCENARIOS

    for scenario in scenarios:
        res = run_single_test(scenario, registry, provider)
        results.append(res)
        time.sleep(1.0)

    print_summary_table(results)

    report_path = PROJECT_ROOT / "reports" / "dynamic_tools_timing_report.json"
    save_json_report(results, report_path)


if __name__ == "__main__":
    main()

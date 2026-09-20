from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "tests" / "benchmark" / "questions.json"
RESULTS_DIR = ROOT / "reports" / "benchmark_runs"
REPORT_PATH = ROOT / "reports" / "benchmark_report.md"


def post_json(url: str, payload: dict, timeout: float) -> dict:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_text(value: str) -> str:
    return value.casefold()


def extract_numbers(text: str) -> list[float]:
    # LLM responses may use typographic Unicode minus signs.
    text = (
        text.replace("−", "-")
        .replace("–", "-")
        .replace("—", "-")
    )
    # 801375.536, 801,375.536, 801.375,536 ve normal integer/decimal
    tokens = re.findall(
        r"(?<![\w])[-+]?\d[\d.,]*(?:[eE][-+]?\d+)?",
        text,
    )

    values: list[float] = []

    for token in tokens:
        x = token.strip().rstrip(".,")
        if not x:
            continue

        # Scientific notation
        if "e" in x.lower():
            try:
                values.append(float(x.replace(",", ".")))
            except ValueError:
                pass
            continue

        comma = x.count(",")
        dot = x.count(".")

        try:
            if comma and dot:
                # Son ayırıcı decimal kabul edilir.
                if x.rfind(",") > x.rfind("."):
                    x = x.replace(".", "").replace(",", ".")
                else:
                    x = x.replace(",", "")
            elif comma:
                parts = x.split(",")
                # 1,234,567 => thousands; 1,71 => decimal
                if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) > 3):
                    x = x.replace(",", "")
                else:
                    x = x.replace(",", ".")
            elif dot:
                parts = x.split(".")
                if len(parts) > 2:
                    # 268.359.123 -> grouped thousands
                    x = x.replace(".", "")
                    values.append(float(x))
                    continue
                elif len(parts) == 2 and len(parts[1]) == 3:
                    # 268.359 hem Türkçe binlik hem gerçek decimal olabilir.
                    # İki adayı da tut; ground-truth eşleşmesi doğru olanı seçsin.
                    values.append(float(x))
                    values.append(float(x.replace(".", "")))
                    continue

            values.append(float(x))
        except ValueError:
            continue

    return values


def number_matches(target: float, answer_numbers: list[float]) -> bool:
    if not math.isfinite(target):
        return False

    # Kullanıcıya sunulan cevaplar çoğunlukla yuvarlanır.
    # Korelasyonlarda sıkı; yüzde/oran değerlerinde makul yuvarlama toleransı.
    if abs(target) < 1:
        abs_tol = 0.005
        rel_tol = 0.005
    elif abs(target) < 100:
        abs_tol = 0.05
        rel_tol = 0.005
    else:
        abs_tol = max(0.5, abs(target) * 0.001)
        rel_tol = 0.001

    for observed in answer_numbers:
        if math.isclose(
            observed,
            target,
            rel_tol=rel_tol,
            abs_tol=abs_tol,
        ):
            return True

    return False


def extract_used_tools(trace: list[dict]) -> list[str]:
    return [
        str(item.get("tool_name"))
        for item in trace
        if item.get("type") == "tool_call" and item.get("tool_name")
    ]


def tool_score(expected: list[str], used: list[str]) -> tuple[float, list[str]]:
    if not expected:
        return 1.0, []

    missing = [tool for tool in expected if tool not in used]
    return (len(expected) - len(missing)) / len(expected), missing


def numeric_score(targets: list[float], answer: str) -> tuple[float, list[float]]:
    if not targets:
        return 1.0, []

    observed = extract_numbers(answer)
    missing = [
        target for target in targets
        if not number_matches(float(target), observed)
    ]
    return (len(targets) - len(missing)) / len(targets), missing


def text_score(required: list[str], answer: str) -> tuple[float, list[str]]:
    if not required:
        return 1.0, []

    normalized = normalize_text(answer)
    missing = [
        value for value in required
        if normalize_text(str(value)) not in normalized
    ]
    return (len(required) - len(missing)) / len(required), missing


def grounding_score(grounding: dict | None) -> float | None:
    if not grounding:
        return None

    checked = int(grounding.get("checked") or 0)
    if checked <= 0:
        return None

    # API'nın döndürdüğü grounded/matched alanlarına toleranslı davran.
    matched = grounding.get("matched")
    if matched is None:
        ungrounded = grounding.get("ungrounded") or []
        matched = max(0, checked - len(ungrounded))

    try:
        return float(matched) / checked
    except Exception:
        return None


def build_report(results: list[dict], provider: str) -> str:
    total = len(results)
    succeeded = sum(1 for r in results if r["request_success"])
    avg_duration = (
        sum(r["duration_s"] for r in results) / total if total else 0.0
    )

    valid_numeric = [r["numeric_score"] for r in results]
    valid_tool = [r["tool_score"] for r in results]
    groundings = [
        r["grounding_score"]
        for r in results
        if r["grounding_score"] is not None
    ]

    by_category: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        by_category[result["category"]].append(result)

    lines = [
        "# NovaData Benchmark Report",
        "",
        f"- Run time: {datetime.now().isoformat(timespec='seconds')}",
        f"- Provider: `{provider}`",
        f"- Questions executed: **{total}**",
        f"- Successful API responses: **{succeeded}/{total}**",
        f"- Average duration: **{avg_duration:.2f}s**",
        f"- Mean expected-tool coverage: **{(sum(valid_tool)/len(valid_tool)*100 if valid_tool else 0):.1f}%**",
        f"- Mean numeric coverage: **{(sum(valid_numeric)/len(valid_numeric)*100 if valid_numeric else 0):.1f}%**",
    ]

    if groundings:
        lines.append(
            f"- Mean grounding coverage: **{sum(groundings)/len(groundings)*100:.1f}%**"
        )

    lines += [
        "",
        "## Category summary",
        "",
        "| Category | N | API success | Tool coverage | Numeric coverage | Avg duration |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for category, rows in sorted(by_category.items()):
        n = len(rows)
        api = sum(1 for r in rows if r["request_success"]) / n * 100
        tools = sum(r["tool_score"] for r in rows) / n * 100
        numeric = sum(r["numeric_score"] for r in rows) / n * 100
        duration = sum(r["duration_s"] for r in rows) / n
        lines.append(
            f"| {category} | {n} | {api:.1f}% | {tools:.1f}% | {numeric:.1f}% | {duration:.2f}s |"
        )

    lines += [
        "",
        "## Per-question results",
        "",
        "| ID | Category | Sec | Tools | Numeric | Text | Grounding | Status |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for r in results:
        grounding = (
            "—"
            if r["grounding_score"] is None
            else f"{r['grounding_score']*100:.0f}%"
        )
        status = "PASS" if r["passed"] else "CHECK"
        lines.append(
            f"| {r['id']} | {r['category']} | {r['duration_s']:.2f} | "
            f"{r['tool_score']*100:.0f}% | {r['numeric_score']*100:.0f}% | "
            f"{r['text_score']*100:.0f}% | {grounding} | {status} |"
        )

    lines += ["", "## Items requiring review", ""]

    review = [r for r in results if not r["passed"]]
    if not review:
        lines.append("No failed/check items.")
    else:
        for r in review:
            lines += [
                f"### {r['id']}",
                "",
                f"- Question: {r['question']}",
                f"- Used tools: `{', '.join(r['used_tools']) or 'none'}`",
                f"- Missing expected tools: `{', '.join(r['missing_tools']) or 'none'}`",
                f"- Missing numbers: `{r['missing_numbers']}`",
                f"- Missing text: `{r['missing_text']}`",
                f"- Error: `{r['error'] or 'none'}`",
                "",
            ]

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--id")
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()

    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))

    if args.id:
        questions = [q for q in questions if q["id"] == args.id]
        if not questions:
            raise SystemExit(f"Question not found: {args.id}")
    else:
        questions = questions[args.start:]
        if args.limit is not None:
            questions = questions[:args.limit]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    for index, q in enumerate(questions, 1):
        print(
            f"[{index}/{len(questions)}] {q['id']} "
            f"({q['category']}) ...",
            flush=True,
        )

        started = time.perf_counter()
        error = None
        response = {}

        try:
            response = post_json(
                f"{args.base_url.rstrip('/')}/api/v1/ask",
                {
                    "question": q["question"],
                    "history": [],
                    "provider": args.provider,
                },
                timeout=args.timeout,
            )
        except urllib.error.HTTPError as exc:
            error = f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:500]}"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        duration = time.perf_counter() - started

        payload = response.get("data") if isinstance(response.get("data"), dict) else response

        answer = str(payload.get("answer") or "")
        trace = payload.get("trace") or []
        grounding = payload.get("grounding")

        used_tools = extract_used_tools(trace)
        t_score, missing_tools = tool_score(
            q.get("expected_tools") or [],
            used_tools,
        )
        n_score, missing_numbers = numeric_score(
            q.get("must_contain_numbers") or [],
            answer,
        )
        x_score, missing_text = text_score(
            q.get("must_contain_text") or [],
            answer,
        )
        g_score = grounding_score(grounding)

        request_success = bool(response.get("success")) and not error

        # Tool selection is diagnostic, not a hard correctness gate:
        # valid answers can sometimes be produced by another deterministic tool.
        passed = (
            request_success
            and n_score == 1.0
            and x_score == 1.0
        )

        result = {
            "id": q["id"],
            "category": q["category"],
            "question": q["question"],
            "verification_mode": q.get("verification_mode"),
            "request_success": request_success,
            "passed": passed,
            "duration_s": round(duration, 3),
            "expected_tools": q.get("expected_tools") or [],
            "used_tools": used_tools,
            "tool_score": round(t_score, 4),
            "missing_tools": missing_tools,
            "numeric_score": round(n_score, 4),
            "missing_numbers": missing_numbers,
            "text_score": round(x_score, 4),
            "missing_text": missing_text,
            "grounding_score": None if g_score is None else round(g_score, 4),
            "grounding": grounding,
            "answer": answer,
            "error": error,
        }
        results.append(result)

        print(
            f"    {duration:.2f}s "
            f"tools={t_score*100:.0f}% "
            f"numbers={n_score*100:.0f}% "
            f"text={x_score*100:.0f}% "
            f"{'PASS' if passed else 'CHECK'}",
            flush=True,
        )

    json_path = RESULTS_DIR / f"benchmark_{run_id}.json"
    json_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = build_report(results, args.provider)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print()
    print(f"Raw results: {json_path}")
    print(f"Report:      {REPORT_PATH}")


if __name__ == "__main__":
    main()

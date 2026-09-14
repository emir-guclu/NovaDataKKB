import json
import logging
import time
from typing import Any, Callable

from pydantic import ValidationError

from backend.app.agent.tool_registry import ToolRegistry
from backend.app.core.llm_provider import KloudeksProvider
from backend.app.prompts.loader import get_system_prompt
from backend.app.prompts.sanitizer import (
    flag_suspicious_content,
    format_safe_user_message,
)

logger = logging.getLogger(__name__)


def _canonical_tool_signature(tool_name: str, arguments_str: str) -> tuple[str, str]:
    try:
        parsed = json.loads(arguments_str)
        canonical_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except Exception:
        canonical_args = arguments_str.strip()
    return (tool_name, canonical_args)


def _collect_sources_from_tool_result(
    tool_name: str,
    result: Any,
    collected_sources: list[dict[str, str]],
) -> None:
    seen_urls = {s["url"] for s in collected_sources if s.get("url")}
    if tool_name == "web_search":
        results = getattr(result, "results", []) or []
        for item in results:
            if isinstance(item, dict):
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip() or url
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    collected_sources.append({"url": url, "title": title})
    elif tool_name == "web_url_reader":
        url = (getattr(result, "url", None) or "").strip()
        title = (getattr(result, "title", None) or "").strip() or url
        if url and url not in seen_urls:
            seen_urls.add(url)
            collected_sources.append({"url": url, "title": title})


def _ensure_citations_in_response(
    text: str,
    collected_sources: list[dict[str, str]],
) -> str:
    if not collected_sources:
        return text

    if "🔗 Kaynaklar" in text or "### Kaynaklar" in text or "## Kaynaklar" in text:
        return text

    citation_lines = ["### 🔗 Kaynaklar"]
    for src in collected_sources:
        title = src.get("title") or src.get("url")
        url = src.get("url")
        if url:
            citation_lines.append(f"- [{title}]({url})")

    return text.rstrip() + "\n\n" + "\n".join(citation_lines)


def run_agent(
    question: str,
    registry: ToolRegistry,
    provider: KloudeksProvider,
    max_iterations: int = 6,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    if max_iterations < 1:
        raise ValueError("max_iterations en az 1 olmali.")

    flag_suspicious_content(question, source_url="user_query")
    safe_user_message = format_safe_user_message(question)

    messages: list[dict] = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": safe_user_message},
    ]
    tools_schema = registry.to_openai_tools_format()
    executed_tool_calls: set[tuple[str, str]] = set()
    collected_sources: list[dict[str, str]] = []
    max_parallel_calls = 2

    for iteration in range(1, max_iterations + 1):
        logger.info(
            "agent iteration=%s/%s question=%r",
            iteration,
            max_iterations,
            question,
        )

        if on_event:
            on_event(
                "llm_input",
                {
                    "iteration": iteration,
                    "question": question,
                    "messages": [dict(m) for m in messages],
                    "tools": tools_schema,
                },
            )

        llm_t0 = time.perf_counter()
        response = provider.chat(messages, tools=tools_schema)
        llm_duration_s = time.perf_counter() - llm_t0

        if not response.tool_calls:
            logger.info("agent finished iteration=%s llm_duration=%.2fs", iteration, llm_duration_s)
            raw_text = response.content or "Model bos cevap dondurdu."
            final_text = _ensure_citations_in_response(raw_text, collected_sources)
            if on_event:
                on_event(
                    "llm_final",
                    {
                        "iteration": iteration,
                        "answer": final_text,
                        "llm_duration_s": llm_duration_s,
                    },
                )
            return final_text

        assistant_tool_calls = []

        for call in response.tool_calls:
            assistant_tool_calls.append(
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": call.arguments,
                    },
                }
            )

        messages.append(
            {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": assistant_tool_calls,
            }
        )

        # Cap parallel tool calls to prevent latency explosion
        calls_to_execute = response.tool_calls[:max_parallel_calls]
        calls_to_skip = response.tool_calls[max_parallel_calls:]

        for call in calls_to_execute:
            logger.info(
                "tool selected iteration=%s tool=%s arguments=%s llm_duration=%.2fs",
                iteration,
                call.name,
                call.arguments,
                llm_duration_s,
            )
            if on_event:
                on_event(
                    "llm_decision",
                    {
                        "iteration": iteration,
                        "call_id": call.id,
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "llm_duration_s": llm_duration_s,
                    },
                )

            tool = registry.get(call.name)

            if tool is None:
                error_message = f"Bu tool kayitli degil: {call.name}"
                logger.warning(error_message)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": error_message,
                    }
                )
                if on_event:
                    on_event(
                        "tool_output",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "result": error_message,
                            "success": False,
                            "tool_duration_s": 0.0,
                        },
                    )
                    on_event(
                        "llm_input_after_tool",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "content": error_message,
                        },
                    )
                continue

            # Anti-Thrashing Guard: check if identical tool + arguments already succeeded
            call_sig = _canonical_tool_signature(call.name, call.arguments)
            if call_sig in executed_tool_calls:
                repeat_message = (
                    "Bu sorgu az once basariyla calistirildi ve sonuc yukaridaki mesajlarda mevcuttur. "
                    "Ayni tool'u tekrar calistirmak gereksizdir. Lutfen eldeki sonuclari yorumlayarak nihai yanitinizi olusturun."
                )
                logger.info("anti-thrashing guard intercepted tool=%s", call.name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": repeat_message,
                    }
                )
                if on_event:
                    on_event(
                        "tool_output",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "result": repeat_message,
                            "success": False,
                            "tool_duration_s": 0.0,
                        },
                    )
                    on_event(
                        "llm_input_after_tool",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "content": repeat_message,
                        },
                    )
                continue

            tool_t0 = time.perf_counter()
            try:
                params = tool.Input.model_validate_json(call.arguments)
                logger.info("tool validated tool=%s params=%s", call.name, params.model_dump())

                result = tool.run(params)
                tool_duration_s = time.perf_counter() - tool_t0
                result_json = result.model_dump_json()

                success = getattr(result, "success", None)
                if success is True:
                    executed_tool_calls.add(call_sig)
                    _collect_sources_from_tool_result(call.name, result, collected_sources)

                logger.info(
                    "tool result tool=%s success=%s duration=%.2fs result=%s",
                    call.name,
                    success,
                    tool_duration_s,
                    result_json,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_json,
                    }
                )
                if on_event:
                    on_event(
                        "tool_output",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "result": result_json,
                            "success": success,
                            "tool_duration_s": tool_duration_s,
                        },
                    )
                    on_event(
                        "llm_input_after_tool",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "content": result_json,
                        },
                    )

            except ValidationError as exc:
                tool_duration_s = time.perf_counter() - tool_t0
                error_message = (
                    f"Bu tool basarisiz oldu: parametre dogrulama hatasi: {exc}"
                )
                logger.warning(
                    "tool validation failed tool=%s error=%s",
                    call.name,
                    exc,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": error_message,
                    }
                )
                if on_event:
                    on_event(
                        "tool_output",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "result": error_message,
                            "success": False,
                            "tool_duration_s": tool_duration_s,
                        },
                    )
                    on_event(
                        "llm_input_after_tool",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "content": error_message,
                        },
                    )

            except Exception as exc:
                tool_duration_s = time.perf_counter() - tool_t0
                logger.exception("tool execution failed tool=%s", call.name)
                error_msg = f"Bu tool basarisiz oldu: {exc}"
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": error_msg,
                    }
                )
                if on_event:
                    on_event(
                        "tool_output",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "result": error_msg,
                            "success": False,
                            "tool_duration_s": tool_duration_s,
                        },
                    )
                    on_event(
                        "llm_input_after_tool",
                        {
                            "iteration": iteration,
                            "call_id": call.id,
                            "tool_name": call.name,
                            "content": error_msg,
                        },
                    )

        # Handle skipped calls due to max_parallel_calls
        for skipped_call in calls_to_skip:
            skipped_msg = (
                "Paralel tool limiti asildi (en fazla 2). "
                "Lutfen once calistirilan tool sonuclarini degerlendirerek yanitinizi olusturun."
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": skipped_call.id,
                    "content": skipped_msg,
                }
            )

    # Graceful Force-Synthesis: if max_iterations is reached, force a synthesis response without tools
    logger.info("agent max_iterations reached; triggering graceful force-synthesis")
    force_synthesis_prompt = (
        "Maksimum adim sinirina gelindi. Artik yeni bir arac cagirma. "
        "Su ana kadar topladigin tum arac sonuclarini analiz ederek kullaniciya "
        "elindeki veriler cercevesinde en eksiksiz ve durust sentez yanitini uret."
    )
    messages.append({"role": "user", "content": force_synthesis_prompt})

    if on_event:
        on_event(
            "llm_input",
            {
                "iteration": max_iterations + 1,
                "question": question,
                "messages": [dict(m) for m in messages],
                "tools": None,
                "is_force_synthesis": True,
            },
        )

    synth_t0 = time.perf_counter()
    synth_response = provider.chat(messages, tools=None)
    synth_duration_s = time.perf_counter() - synth_t0

    raw_text = synth_response.content or "Mevcut bilgilerle guvenilir bir son sentez cevabi uretilemedi."
    final_text = _ensure_citations_in_response(raw_text, collected_sources)
    logger.info("graceful force-synthesis completed in %.2fs", synth_duration_s)

    if on_event:
        on_event(
            "llm_final",
            {
                "iteration": max_iterations + 1,
                "answer": final_text,
                "llm_duration_s": synth_duration_s,
                "is_force_synthesis": True,
            },
        )

    return final_text

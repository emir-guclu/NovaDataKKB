import json
import logging
import time
from datetime import date
from typing import Any, Callable

from pydantic import ValidationError

from backend.app.agent.tool_registry import ToolRegistry
from backend.app.core.llm_provider import KloudeksProvider

logger = logging.getLogger(__name__)


def _canonical_tool_signature(tool_name: str, arguments_str: str) -> tuple[str, str]:
    try:
        parsed = json.loads(arguments_str)
        canonical_args = json.dumps(parsed, sort_keys=True, ensure_ascii=False)
    except Exception:
        canonical_args = arguments_str.strip()
    return (tool_name, canonical_args)


def run_agent(
    question: str,
    registry: ToolRegistry,
    provider: KloudeksProvider,
    max_iterations: int = 6,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> str:
    if max_iterations < 1:
        raise ValueError("max_iterations en az 1 olmali.")

    messages: list[dict] = [
        {
            "role": "system",
            "content": (
                f"Sen finansal veri analiz ajanisin. Bugunun tarihi {date.today().isoformat()}. "
                "Kullanici sorusunu cevaplamak icin gereken toolu sec. "
                "Kullanici guncel, son, en yeni veya latest bilgi istiyorsa arama sorgusunda "
                "bugunun yilini/tarihini dikkate al ve daha eski sonucu en guncelmis gibi sunma. "
                "Bir tool basarili olup soruyu cevaplamak icin yeterli ve ilgili veri dondurdugunde "
                "ayni toolu benzer sorgularla gereksiz yere tekrar cagirma; mevcut tool sonucunu "
                "yorumlayip final cevabi ver. Tool sonucu basarisizsa veya gercekten yetersizse "
                "baska bir tool ya da farkli parametrelerle tekrar deneyebilirsin. "
                "Kullanici belirli bir finansal gosterge, kredi turu, faiz, sektor veya makroekonomik veri "
                "sordugunda HER ZAMAN ONCE series_catalog_search aracini kullanarak sistemde bu seriyi ara. "
                "Eger ilgili seri yerelde bulunursa donen series_id uzerinden lakehouse_query veya change_detection cagrisi yap. "
                "YALNIZCA serinin yerel katalogda bulunamadigi anlasilirsa (found_in_lakehouse=false veya yetersizse) "
                "ve konu Merkez Bankasi / TCMB makroekonomik verisi ise evds_data_service aracina basvur: "
                "once resmi EVDS katalogunda ara (action='search'), ardindan bulunan seri kodunu canli yukle (action='load'). "
                "Diger harici bilgi ihtiyaclarinda web_search aracina basvur. "
                "Uydurma veri kullanma. Tool sonucunda acikca desteklenmeyen sayisal deger, tarih, alinti veya iddia ekleme. "
                "URL tahmin ederek uydurma; sayfada acikca listelenmeyen hicbir URL'yi kullanma. "
                "web_url_reader sonucundaki Bulunan Dosyalar veya Gorseller listesinde gercek bir URL varsa, "
                "kullanici ilgili rapor, tablo, sema veya gorsel hakkinda ayrinti istediginde ikinci adimda o URL'yi oku. "
                "Eger bir sayfadaki sayisal veriler veya tablolar ham HTML'de bossa ya da JavaScript ile yuklendigi anlasiliyorsa, "
                "ayni URL'yi web_url_reader ile render_js=True parametresi vererek tekrar oku. "
                "Bir bilgi tool sonucunda yoksa bunu kesin gercek gibi yazma. "
                "Tool sonucundan dogrudan cikmayan trend, yayin takvimi, beklenti veya ek sayisal yorum uretme. "
                "Yalnizca tool sonucunda acikca desteklenen gercekleri ve bu gerceklerin basit yorumunu kullan."
            ),
        },
        {"role": "user", "content": question},
    ]
    tools_schema = registry.to_openai_tools_format()
    executed_tool_calls: set[tuple[str, str]] = set()
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
            final_text = response.content or "Model bos cevap dondurdu."
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

    final_text = synth_response.content or "Mevcut bilgilerle guvenilir bir son sentez cevabi uretilemedi."
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

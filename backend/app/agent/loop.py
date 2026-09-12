from __future__ import annotations

import logging
from datetime import date

from pydantic import ValidationError

from backend.app.agent.tool_registry import ToolRegistry
from backend.app.core.llm_provider import KloudeksProvider

logger = logging.getLogger(__name__)


def run_agent(
    question: str,
    registry: ToolRegistry,
    provider: KloudeksProvider,
    max_iterations: int = 6,
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
                "Uydurma veri kullanma. Tool sonucunda acikca desteklenmeyen sayisal deger, tarih, alinti veya iddia ekleme. "
                "Bir bilgi tool sonucunda yoksa bunu kesin gercek gibi yazma. "
                "Tool sonucundan dogrudan cikmayan trend, yayin takvimi, beklenti veya ek sayisal yorum uretme. "
                "Yalnizca tool sonucunda acikca desteklenen gercekleri ve bu gerceklerin basit yorumunu kullan."
            ),
        },
        {"role": "user", "content": question},
    ]
    tools_schema = registry.to_openai_tools_format()

    for iteration in range(1, max_iterations + 1):
        logger.info(
            "agent iteration=%s/%s question=%r",
            iteration,
            max_iterations,
            question,
        )

        response = provider.chat(messages, tools=tools_schema)

        if not response.tool_calls:
            logger.info("agent finished iteration=%s", iteration)
            return response.content or "Model bos cevap dondurdu."

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

        for call in response.tool_calls:
            logger.info(
                "tool selected iteration=%s tool=%s arguments=%s",
                iteration,
                call.name,
                call.arguments,
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
                continue

            try:
                params = tool.Input.model_validate_json(call.arguments)
                logger.info("tool validated tool=%s params=%s", call.name, params.model_dump())

                result = tool.run(params)
                result_json = result.model_dump_json()

                logger.info(
                    "tool result tool=%s success=%s result=%s",
                    call.name,
                    getattr(result, "success", None),
                    result_json,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": result_json,
                    }
                )

            except ValidationError as exc:
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

            except Exception as exc:
                logger.exception("tool execution failed tool=%s", call.name)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"Bu tool basarisiz oldu: {exc}",
                    }
                )

    logger.warning("agent max_iterations reached max_iterations=%s", max_iterations)
    return "Maksimum adim sayisina ulasildi; mevcut bilgilerle guvenilir bir son cevap uretilemedi."

from __future__ import annotations
import base64
import os

import httpx
import structlog
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

log = structlog.get_logger()

_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
_AGENT_URL = os.getenv("FOOD_RESCUE_AGENT_URL", "http://localhost:8080")
_API_KEY = os.getenv("FOOD_RESCUE_API_KEY", "")
_HITL_BYPASS = os.getenv("HITL_BYPASS", "false").lower() == "true"

_HEADERS = {"X-API-Key": _API_KEY}


async def _call_agent(text: str, images: list[str], platform: str = "telegram") -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{_AGENT_URL}/analyze",
            json={"text": text, "images": images, "platform": platform},
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🌿 CulinaAI Food Rescue aktif!\n"
        "Bozulmak üzere olan malzemelerinizin fotoğrafını gönderin veya "
        "/rescue komutunu kullanın."
    )


async def cmd_rescue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "Lütfen malzemeleri yazın. Örnek:\n"
            "/rescue ıspanak, domates, kıyma - bugün kullanmam lazım"
        )
        return

    await update.message.reply_text("Analiz ediyorum... 🔍")

    try:
        result = await _call_agent(text=text, images=[], platform="telegram")
    except Exception as exc:
        log.error("telegram_rescue_api_error", error=str(exc))
        await update.message.reply_text("Bir hata oluştu, lütfen tekrar deneyin.")
        return

    if not result.get("is_food_rescue"):
        await update.message.reply_text(
            "Bu mesajda food rescue sinyali bulamadım. "
            "Bozulmak üzere malzemeleriniz varsa daha açık yazabilir misiniz?"
        )
        return

    await _send_or_queue(update, result)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Analiz ediyorum... 🔍")

    # Download the highest resolution photo
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()
    b64_image = base64.b64encode(bytes(file_bytes)).decode()

    caption = update.message.caption or ""

    try:
        result = await _call_agent(text=caption, images=[b64_image], platform="telegram")
    except Exception as exc:
        log.error("telegram_photo_api_error", error=str(exc))
        await update.message.reply_text("Analiz sırasında hata oluştu, lütfen tekrar deneyin.")
        return

    if not result.get("is_food_rescue"):
        await update.message.reply_text(
            "Görselde food rescue durumu tespit edemedim. "
            "Bozulmak üzere malzemeleriniz varsa caption'a yazabilirsiniz."
        )
        return

    await _send_or_queue(update, result)


async def _send_or_queue(update: Update, result: dict) -> None:
    reply_content = result.get("reply_draft", {}).get("content", "")
    if not reply_content:
        await update.message.reply_text("Kurtarma planı oluşturulamadı.")
        return

    if _HITL_BYPASS:
        await update.message.reply_text(reply_content)
    else:
        await update.message.reply_text(
            "Kurtarma planınız hazırlandı! Moderatör onayını bekliyor. "
            "En kısa sürede yanıt gönderilecek. 🌿"
        )
        log.info("telegram_queued_for_hitl", analysis_id=result.get("analysis_id"))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_AGENT_URL}/metrics", headers=_HEADERS)
            data = resp.json()
        await update.message.reply_text(
            f"📊 İstatistikler:\n"
            f"• Toplam analiz: {data.get('processed', 0)}\n"
            f"• Onaylanan: {data.get('approved', 0)}\n"
            f"• Ort. süre: {data.get('avg_latency_ms', 0):.0f}ms"
        )
    except Exception:
        await update.message.reply_text("İstatistikler şu an alınamıyor.")


def build_application() -> Application:
    app = (
        Application.builder()
        .token(_BOT_TOKEN)
        .secret_token(_WEBHOOK_SECRET)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("rescue", cmd_rescue))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    return app


if __name__ == "__main__":
    application = build_application()
    application.run_polling()

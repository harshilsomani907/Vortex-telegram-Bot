import base64
import logging
import os
import subprocess
import tempfile

import requests
from dotenv import load_dotenv
from gtts import gTTS
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

ERROR_HIGH_DEMAND = "Vortex AI is currently experiencing high demand. Please try sending your message again in a few moments."
MAX_FILE_SIZE = 20 * 1024 * 1024  # Telegram's own limit

SYSTEM_PROMPT = (
    "You are Vortex, a smart, friendly, and helpful Telegram bot assistant. "
    "Always answer briefly and to the point — a few short sentences at most, no long explanations "
    "unless the user explicitly asks for more detail. Avoid unnecessary fluff, remain professional yet "
    "warm, and never mention that you are an AI or made by Google."
)

GEMINI_MODELS = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ── Gemini ───────────────────────────────────────────────────────────────

def ask_gemini(user_message: str = None, voice_data: bytes = None, mime_type: str = None) -> str:
    """Send text and/or audio to Gemini, trying each model until one works."""
    parts = []
    if voice_data and mime_type:
        parts.append({"inlineData": {
            "mimeType": mime_type.split(";")[0].strip(),
            "data": base64.b64encode(voice_data).decode("utf-8"),
        }})
    if user_message:
        parts.append({"text": user_message})
    elif voice_data:
        parts.append({"text": "Please listen to the voice message and respond to it."})

    if not parts:
        return "I received an empty message."

    last_error = "unknown error"
    for model in GEMINI_MODELS:
        payload = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": 8000},
        }
        if model == "gemini-3.5-flash":
            payload["generationConfig"]["thinkingConfig"] = {"thinkingLevel": "MINIMAL"}

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            resp = requests.post(url, json=payload, timeout=30)
        except Exception as e:
            last_error = f"{model} exception: {e}"
            logger.warning(last_error)
            continue

        if resp.status_code != 200:
            last_error = f"{model} failed with status {resp.status_code}"
            logger.warning(last_error)
            continue

        candidates = resp.json().get("candidates", [])
        reply_parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        if reply_parts and "text" in reply_parts[0]:
            return reply_parts[0]["text"].strip()

        last_error = f"{model} returned no usable text"
        logger.warning(last_error)

    logger.error(f"All Gemini models failed. Last error: {last_error}")
    return ERROR_HIGH_DEMAND


# ── Audio helpers ────────────────────────────────────────────────────────

def _run_ffmpeg(args: list) -> None:
    subprocess.run(["ffmpeg", "-y", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def convert_to_mp3(audio_bytes: bytes) -> bytes:
    """Normalize any incoming audio to a small mp3 via ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as src:
        src.write(audio_bytes)
    out_path = src.name + ".mp3"
    try:
        _run_ffmpeg(["-i", src.name, "-vn", "-ar", "16000", "-ac", "1", "-b:a", "32k", out_path])
        with open(out_path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Failed to convert audio to MP3: {e}")
        return audio_bytes
    finally:
        for path in (src.name, out_path):
            if os.path.exists(path):
                os.unlink(path)


def text_to_ogg(text: str) -> str | None:
    """Turn text into a voice note (OGG/Opus). Falls back to MP3 if ffmpeg fails."""
    mp3_path = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    try:
        gTTS(text=text, lang="en", slow=False).save(mp3_path)
    except Exception as e:
        logger.error(f"gTTS failed: {e}")
        return None

    ogg_path = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False).name
    try:
        _run_ffmpeg(["-i", mp3_path, "-c:a", "libopus", ogg_path])
        os.unlink(mp3_path)
        return ogg_path
    except Exception as e:
        logger.error(f"ffmpeg conversion error: {e}. Falling back to MP3.")
        if os.path.exists(ogg_path):
            os.unlink(ogg_path)
        return mp3_path


# ── Telegram handlers ────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🚀 *Welcome to Vortex AI* 🔥\n\n"
        "I am your advanced, high-performance virtual assistant powered by state-of-the-art AI. "
        "Here is what I can do for you:\n\n"
        "🧠 *Smart AI Reply*: Send me a text, voice message, or audio file, and I will generate an "
        "intelligent, helpful response.\n"
        "🎙️ *Voice Response*: I will also deliver my AI response read aloud as a voice note!\n\n"
        "Go ahead—ask me anything, send a voice note, or say hello! 👇",
        parse_mode="Markdown",
    )


async def _download_audio(tg_file, fallback_mime: str) -> tuple[bytes, str]:
    """Download a Telegram file and convert it to mp3, falling back to the raw bytes on failure."""
    raw = bytes(await (await tg_file.get_file()).download_as_bytearray())
    try:
        return convert_to_mp3(raw), "audio/mp3"
    except Exception as e:
        logger.warning(f"Audio conversion failed: {e}. Sending raw.")
        return raw, fallback_mime


UNSUPPORTED_MSG = "⚠️ Vortex AI currently only supports text, voice notes, and audio files. Please send your question as text or voice!"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Text/voice in → Gemini reply out, as both text and a spoken voice note."""
    if not update.message:
        return

    msg = update.message
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name if update.effective_user else "Unknown User"
    voice_data = mime_type = None
    user_text = msg.text

    try:
        audio_source = msg.voice or msg.audio
        doc_is_audio = msg.document and (msg.document.mime_type or "").startswith("audio/")

        if audio_source or doc_is_audio:
            source = audio_source or msg.document
            if source.file_size and source.file_size > MAX_FILE_SIZE:
                await msg.reply_text("⚠️ That file is too large. Please send something under 20MB.")
                return

            logger.info(f"[{user_name}] Sent an audio message")
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            fallback_mime = source.mime_type or "audio/ogg"
            voice_data, mime_type = await _download_audio(source, fallback_mime)
            if msg.caption:
                user_text = msg.caption

        elif msg.document or msg.photo or msg.video or msg.animation or msg.sticker:
            logger.info(f"[{user_name}] Sent unsupported media")
            await msg.reply_text(UNSUPPORTED_MSG)
            return

        elif user_text:
            logger.info(f"[{user_name}] {user_text}")

        else:
            logger.info(f"[{user_name}] Sent empty or unsupported message")
            await msg.reply_text(UNSUPPORTED_MSG)
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        gemini_reply = ask_gemini(user_message=user_text, voice_data=voice_data, mime_type=mime_type)
        await msg.reply_text(f"🤖 {gemini_reply}")

        if gemini_reply == ERROR_HIGH_DEMAND:
            return

        await context.bot.send_chat_action(chat_id=chat_id, action="record_voice")
        ogg_path = None
        try:
            ogg_path = text_to_ogg(gemini_reply)
            if ogg_path and os.path.exists(ogg_path):
                with open(ogg_path, "rb") as voice_file:
                    await msg.reply_voice(voice=voice_file, caption="🔊 Vortex voice reply")
            else:
                logger.warning("Could not generate a voice reply.")
        except Exception as e:
            logger.error(f"Voice send error: {e}")
        finally:
            if ogg_path and os.path.exists(ogg_path):
                os.unlink(ogg_path)

    except Exception as e:
        logger.error(f"General message handling error: {e}", exc_info=True)
        await msg.reply_text("⚠️ Sorry, I encountered an error while processing your message.")


# ── Entry point ──────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        print("[ERROR] Set your BOT_TOKEN in the .env file or environment!")
        return
    if not GEMINI_API_KEY:
        print("[ERROR] Set your GEMINI_API_KEY in the .env file or environment!")
        return

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))

    print("[SUCCESS] Vortex bot is live! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()

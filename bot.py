import logging
import os
import tempfile
import requests
from dotenv import load_dotenv
from gtts import gTTS
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Load environment variables from .env file
load_dotenv()

# ─────────────────────────────────────────────
#  CONFIGURATION  — environment variables loaded from .env
# ─────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Text message sent immediately when a user writes anything
WELCOME_TEXT = "Welcome! Thanks for messaging Vortex 🔥"

# AI system prompt — controls the bot's personality
SYSTEM_PROMPT = (
    "You are Vortex, a smart, friendly, and helpful Telegram bot assistant. "
    "Provide crisp, short, and to-the-point answers directly addressing the user's message. "
    "Keep your response warm, concise, and no longer than 1-2 sentences. "
    "Never mention that you are an AI or made by Google."
)
# ─────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Gemini API helper ──────────────────────────────────────────────────────────

def ask_gemini(user_message: str) -> str:
    """Send a message to Gemini and return the text reply."""
    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {
            "maxOutputTokens": 8000,
        }
    }
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20,
        )
        if resp.status_code != 200:
            logger.error(f"Gemini API returned status {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        if 'resp' in locals() and hasattr(resp, 'text'):
            try:
                err_msg = resp.json().get('error', {}).get('message', resp.text)
                return f"Sorry, I couldn't generate a response right now. (Error: {err_msg})"
            except Exception:
                return f"Sorry, I couldn't generate a response right now. (Error: {resp.text[:100]})"
        return f"Sorry, I couldn't generate a response right now. (Error: {e})"


# ── Text-to-Speech helper ──────────────────────────────────────────────────────

def text_to_ogg(text: str) -> str:
    """Convert text to a .ogg voice file and return the temp file path."""
    tts = gTTS(text=text, lang="en", slow=False)
    tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    tmp.close()
    tts.save(tmp.name)
    return tmp.name


# ── Telegram handlers ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "🚀 *Welcome to Vortex AI* 🔥\n\n"
        "I am your advanced, high-performance virtual assistant powered by state-of-the-art AI. "
        "Here is what I will do for every message you send:\n\n"
        "⚡ *Instant Welcome*: Send a quick acknowledgement.\n"
        "🧠 *Smart AI Reply*: Generate a detailed, intelligent, and helpful response.\n"
        "🎙️ *Voice Message*: Deliver the AI response read aloud as a voice note!\n\n"
        "Go ahead—ask me anything or say hello! 👇",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Full flow:
      1. Send welcome text immediately
      2. Ask Gemini for a smart reply
      3. Send Gemini's reply as text
      4. Convert Gemini's reply to voice and send as audio
    """
    user = update.effective_user
    user_text = update.message.text
    logger.info(f"[{user.first_name}] {user_text}")

    # ── Step 1: Welcome text ───────────────────────────────────────────────────
    await update.message.reply_text(WELCOME_TEXT)

    # ── Step 2: Typing indicator while Gemini thinks ───────────────────────────
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # ── Step 3: Get Gemini's reply ─────────────────────────────────────────────
    gemini_reply = ask_gemini(user_text)

    # ── Step 4: Send Gemini's reply as text ───────────────────────────────────
    await update.message.reply_text(f"🤖 {gemini_reply}")

    # ── Step 5: Convert to voice and send ─────────────────────────────────────
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="record_voice"
    )

    ogg_path = None
    try:
        ogg_path = text_to_ogg(gemini_reply)
        with open(ogg_path, "rb") as voice_file:
            await update.message.reply_voice(
                voice=voice_file,
                caption="🔊 Vortex voice reply",
            )
    except Exception as e:
        logger.error(f"Voice send error: {e}")
        await update.message.reply_text("⚠️ Couldn't send voice message right now.")
    finally:
        if ogg_path and os.path.exists(ogg_path):
            os.unlink(ogg_path)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        print("[ERROR] Set your BOT_TOKEN in the .env file or environment!")
        return
    if not GEMINI_API_KEY:
        print("[ERROR] Set your GEMINI_API_KEY in the .env file or environment!")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("[SUCCESS] Vortex bot is live! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

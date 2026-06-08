import logging
import os
import time
import tempfile
import requests
import subprocess
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
    "Provide crisp, highly accurate, and directly meaningful answers addressing the user's query in full. "
    "Keep your response clear, structured, and engaging, ensuring all aspects of the user's question or requirements are completely fulfilled. "
    "Avoid unnecessary fluff, remain professional yet warm, and never mention that you are an AI or made by Google."
)
# ─────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Gemini API helper ──────────────────────────────────────────────────────────

def ask_gemini(user_message: str = None, voice_data: bytes = None, mime_type: str = None) -> str:
    """Send a message/audio to Gemini and return the text reply, with robust retries and fallbacks."""
    headers = {
        "Content-Type": "application/json",
    }
    
    parts = []
    if voice_data and mime_type:
        import base64
        encoded_data = base64.b64encode(voice_data).decode("utf-8")
        clean_mime_type = mime_type.split(";")[0].strip()
        parts.append({
            "inlineData": {
                "mimeType": clean_mime_type,
                "data": encoded_data
            }
        })
    
    if user_message:
        parts.append({"text": user_message})
    elif voice_data:
        parts.append({"text": "Please listen to the voice message and respond to it."})
        
    if not parts:
        return "I received an empty message."

    # List of models to try (prioritizing 3.5-flash, with 2.5-flash fallback if quota is exceeded)
    models = ["gemini-3.5-flash", "gemini-2.5-flash"]
    last_error = "Unknown error"
    
    for model in models:
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [{"parts": parts}],
            "generationConfig": {
                "maxOutputTokens": 8000
            }
        }
        
        # Add thinkingConfig only for the 3.5-flash model
        if model == "gemini-3.5-flash":
            payload["generationConfig"]["thinkingConfig"] = {
                "thinkingLevel": "MINIMAL"
            }
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        
        # Retry up to 2 times with backoff only on transient 503 errors
        retries = 2
        backoff = 1.0
        
        for attempt in range(retries):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                elif resp.status_code == 429:
                    # Quota exhausted — skip immediately to next model, no point retrying
                    last_error = f"{model} quota exhausted (429)"
                    logger.warning(f"{model} quota exhausted (429). Skipping to next model...")
                    break
                elif resp.status_code == 503:
                    # Transient overload — worth retrying after a short wait
                    last_error = f"{model} overloaded (503)"
                    logger.warning(f"{model} overloaded (503) on attempt {attempt+1}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    backoff *= 2.0
                else:
                    last_error = f"Gemini API returned status {resp.status_code}: {resp.text}"
                    logger.warning(f"{model} failed with status {resp.status_code}. Skipping...")
                    break
            except Exception as e:
                last_error = str(e)
                logger.warning(f"{model} exception on attempt {attempt+1}: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff *= 2.0
                
    logger.error(f"All Gemini models failed. Last error: {last_error}")
    return "Vortex AI is currently experiencing high demand. Please try sending your message again in a few moments."


# ── Audio conversion helpers ──────────────────────────────────────────────────

def convert_to_mp3(audio_bytes: bytes) -> bytes:
    """Convert any incoming audio bytes to standard mp3 bytes using ffmpeg."""
    in_tmp = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
    in_tmp.write(audio_bytes)
    in_tmp.close()
    
    out_tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    out_tmp.close()
    
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", in_tmp.name,
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "32k",
            out_tmp.name
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        with open(out_tmp.name, "rb") as f:
            converted_bytes = f.read()
        return converted_bytes
    except Exception as e:
        logger.error(f"Failed to convert audio to MP3: {e}")
        return audio_bytes  # Return original if ffmpeg fails
    finally:
        if os.path.exists(in_tmp.name):
            os.unlink(in_tmp.name)
        if os.path.exists(out_tmp.name):
            os.unlink(out_tmp.name)


def text_to_ogg(text: str) -> str:
    """Convert text to a proper OGG Opus voice file using ffmpeg and return the path."""
    tts = gTTS(text=text, lang="en", slow=False)
    
    mp3_tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    mp3_tmp.close()
    tts.save(mp3_tmp.name)
    
    ogg_tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
    ogg_tmp.close()
    
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-i", mp3_tmp.name,
            "-c:a", "libopus",
            ogg_tmp.name
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return ogg_tmp.name
    except Exception as e:
        logger.error(f"ffmpeg conversion error: {e}. Falling back to raw gTTS output.")
        if os.path.exists(ogg_tmp.name):
            os.unlink(ogg_tmp.name)
        return mp3_tmp.name
    finally:
        if os.path.exists(mp3_tmp.name):
            os.unlink(mp3_tmp.name)


# ── Telegram handlers ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "🚀 *Welcome to Vortex AI* 🔥\n\n"
        "I am your advanced, high-performance virtual assistant powered by state-of-the-art AI. "
        "Here is what I can do for you:\n\n"
        "🧠 *Smart AI Reply*: Send me a text, voice message, or audio file, and I will generate an intelligent, helpful response.\n"
        "🎙️ *Voice Response*: I will also deliver my AI response read aloud as a voice note!\n\n"
        "Go ahead—ask me anything, send a voice note, or say hello! 👇",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Full flow:
      1. Detect if it's text or voice/audio message
      2. Download voice/audio if present (enforcing size limits and converting formats)
      3. Ask Gemini for a reply
      4. Send Gemini's reply as text
      5. Convert Gemini's reply to voice and send as audio
    """
    if not update.message:
        return

    user = update.effective_user
    user_name = user.first_name if user else "Unknown User"
    MAX_FILE_SIZE = 20 * 1024 * 1024  # Telegram Bot API limit is 20MB
    try:
        voice_data = None
        mime_type = None
        user_text = update.message.text

        # Check if voice is present
        if update.message.voice:
            if update.message.voice.file_size and update.message.voice.file_size > MAX_FILE_SIZE:
                await update.message.reply_text("⚠️ This voice message is too large. Please send a shorter voice message (max 20MB).")
                return
                
            logger.info(f"[{user_name}] Sent a voice message")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            
            voice_file = await update.message.voice.get_file()
            raw_voice_bytes = bytes(await voice_file.download_as_bytearray())
            
            try:
                voice_data = convert_to_mp3(raw_voice_bytes)
                mime_type = "audio/mp3"
            except Exception as conv_err:
                logger.warning(f"Audio conversion failed: {conv_err}. Sending raw.")
                voice_data = raw_voice_bytes
                mime_type = update.message.voice.mime_type or "audio/ogg"
            
            if update.message.caption:
                user_text = update.message.caption

        # Check if audio is present
        elif update.message.audio:
            if update.message.audio.file_size and update.message.audio.file_size > MAX_FILE_SIZE:
                await update.message.reply_text("⚠️ This audio file is too large. Please send an audio file smaller than 20MB.")
                return
                
            logger.info(f"[{user_name}] Sent an audio file")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            
            audio_file = await update.message.audio.get_file()
            raw_audio_bytes = bytes(await audio_file.download_as_bytearray())
            
            try:
                voice_data = convert_to_mp3(raw_audio_bytes)
                mime_type = "audio/mp3"
            except Exception as conv_err:
                logger.warning(f"Audio conversion failed: {conv_err}. Sending raw.")
                voice_data = raw_audio_bytes
                mime_type = update.message.audio.mime_type or "audio/mp3"
            
            if update.message.caption:
                user_text = update.message.caption

        # Check if document is present (covers audio sent as document/file)
        elif update.message.document:
            doc_mime = update.message.document.mime_type or ""
            if doc_mime.startswith("audio/"):
                if update.message.document.file_size and update.message.document.file_size > MAX_FILE_SIZE:
                    await update.message.reply_text("⚠️ This audio file is too large. Please send a file smaller than 20MB.")
                    return
                    
                logger.info(f"[{user_name}] Sent an audio document: {update.message.document.file_name}")
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                
                doc_file = await update.message.document.get_file()
                raw_audio_bytes = bytes(await doc_file.download_as_bytearray())
                
                try:
                    voice_data = convert_to_mp3(raw_audio_bytes)
                    mime_type = "audio/mp3"
                except Exception as conv_err:
                    logger.warning(f"Audio conversion failed: {conv_err}. Sending raw.")
                    voice_data = raw_audio_bytes
                    mime_type = doc_mime
                
                if update.message.caption:
                    user_text = update.message.caption
            else:
                logger.info(f"[{user_name}] Sent an unsupported document: {update.message.document.file_name}")
                await update.message.reply_text("⚠️ Vortex AI currently only supports text, voice notes, and audio files. Please send your question as text or voice!")
                return

        # Check if unsupported media types are sent
        elif update.message.photo or update.message.video or update.message.animation or update.message.sticker:
            logger.info(f"[{user_name}] Sent unsupported media")
            await update.message.reply_text("⚠️ Vortex AI currently only supports text, voice notes, and audio files. Please send your question as text or voice!")
            return

        elif user_text:
            logger.info(f"[{user_name}] {user_text}")

        else:
            logger.info(f"[{user_name}] Sent empty or unsupported message")
            await update.message.reply_text("⚠️ Vortex AI currently only supports text, voice notes, and audio files. Please send your question as text or voice!")
            return

        # ── Step 2: Typing indicator while Gemini thinks ───────────────────────────
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="typing"
        )

        # ── Step 3: Get Gemini's reply ─────────────────────────────────────────────
        gemini_reply = ask_gemini(user_message=user_text, voice_data=voice_data, mime_type=mime_type)

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

    except Exception as general_err:
        logger.error(f"General message handling error: {general_err}", exc_info=True)
        await update.message.reply_text("⚠️ Sorry, I encountered an error while processing your message.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

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

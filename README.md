# 🔥 Vortex Telegram Bot — Setup Guide

## What the bot does
Every time a user sends a message:
1. ✉️  Instantly replies → "Welcome! Thanks for messaging Vortex 🔥"
2. 🤖  Gemini AI reads the message and generates a smart reply (text)
3. 🎙️  That Gemini reply is spoken aloud and sent as a voice note

---

## Step-by-step Setup

### 1. Get your Telegram Bot Token
1. Open Telegram → search **@BotFather**
2. Send `/newbot`
3. Name it **Vortex_786_Bot**
4. Copy the token you receive (looks like `123456:ABCdef...`)

### 2. Get your Gemini API Key
1. Go to Google AI Studio → https://aistudio.google.com/
2. Sign up / log in and create an API Key
3. Copy the key

### 3. Install Python dependencies
```bash
pip install -r requirements.txt python-dotenv
```

### 4. Configure Environment Variables
Create a `.env` file in the project directory:
```env
BOT_TOKEN=your_telegram_token_here
GEMINI_API_KEY=your_gemini_key_here
```

### 5. Run the bot
```bash
python bot.py
```

### 6. Test it!
- Open Telegram → find your bot → send `/start`
- Then send any message like "Hello!" or "What is AI?"
- You'll get: welcome text → Gemini text reply → Gemini voice note 🎙️

---

## Customize the bot

In `bot.py`, edit these lines:

```python
# Change the first text reply
WELCOME_TEXT = "Welcome! Thanks for messaging Vortex 🔥"

# Change the bot's personality/style
SYSTEM_PROMPT = (
    "You are Vortex, a smart, friendly Telegram bot assistant..."
)
```

---

## Run 24/7 for free

### Railway (easiest)
1. Go to https://railway.app → sign up with GitHub
2. New Project → Deploy from GitHub repo (upload your files)
3. Add environment variables in variables settings: `BOT_TOKEN` and `GEMINI_API_KEY`
4. Done — your bot runs forever!

### Render
1. Go to https://render.com
2. New → Web Service → connect repo
3. Build command: `pip install -r requirements.txt python-dotenv`
4. Start command: `python bot.py`
5. Add environment variables → Deploy

---

## File Structure
```
vortex_bot/
├── bot.py           ← Main bot code
├── .env             ← API Keys & secrets (ignored by git)
├── requirements.txt ← Python packages
└── README.md        ← This guide
```


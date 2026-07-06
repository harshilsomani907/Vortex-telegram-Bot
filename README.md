# Vortex AI Telegram Bot 🤖

An AI-powered Telegram bot built with **Python** and **Google Gemini AI** that automatically responds to user messages with intelligent text and voice replies.

## Features

* 🤖 AI-powered conversations using Google Gemini AI
* 💬 Automatic welcome message for new users
* 🎙️ Converts AI-generated responses into voice messages
* 🔐 Secure API key management using environment variables
* ☁️ Deployed on Railway for continuous availability

## Tech Stack

* Python
* Telegram Bot API
* Google Gemini AI
* python-dotenv
* Railway

## Project Structure

```text
vortex_bot/
├── bot.py
├── requirements.txt
├── .env.example
└── README.md
```

## Installation

```bash
git clone <repository-url>
cd vortex_bot
pip install -r requirements.txt
```

Create a `.env` file:

```env
BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
```

Run the bot:

```bash
python bot.py
```
## link of bot - 

https://t.me/Vortex_786_Bot
## Deployment

The bot is deployed on Railway using environment variables for secure credential management.

## License

This project is intended for educational and portfolio purposes.

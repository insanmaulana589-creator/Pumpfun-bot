import os
import logging
import asyncio
import json
import aiohttp
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")

scan_active = False
buy_amount = 0.2
max_mcap = 50000
tracked_tokens = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 Pumpfun Trading Bot\n\n"
        "⚙️ Setting:\n"
        "💰 Buy: 0.2 SOL\n"
        "📊 Max MCap: $50,000\n"
        "🎯 Take Profit: 2x\n\n"
        "/scan - Mulai scan\n"
        "/stopscan - Stop

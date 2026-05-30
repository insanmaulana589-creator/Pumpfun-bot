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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Pumpfun Scanner\n"
        "/scan - Mulai\n"
        "/stopscan - Stop\n"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

async def scan_tokens(chat_id, app):
    global scan_active
    seen = set()
    await app.bot.send_message(chat_id, "Scanning...")
    while scan_active:
        try:
            async with websockets.connect("wss://pumpportal.fun/api/data") as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                async with aiohttp.ClientSession() as session:
                    while scan_active:
                        try:
                            data = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                            mint = data.get("mint", "")
                            if not mint or mint in seen:
                                

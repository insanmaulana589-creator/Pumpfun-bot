import os
import logging
import asyncio
import aiohttp
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
        "⚙️ Setting aktif:\n"
        f"💰 Buy: {buy_amount} SOL\n"
        f"📊 Max MCap: $50,000\n"
        f"🎯 Take Profit: 2x\n\n"
        "/scan - Mulai scan\n"
        "/stopscan - Stop scan\n"
        "/positions - Lihat posisi\n"
        "/help - Bantuan"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("🛑 Scanning dihentikan!")

async def positions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not tracked_tokens:
        await update.message.reply_text("📭 Tidak ada posisi aktif.")
        return
    msg = "📊 Posisi Aktif:\n\n"
    for mint, data in tracked_tokens.items():
        msg += (
            f"📛 {data['name']} (${data['symbol']})\n"
            f"💰 Buy MCap: ${data['buy_mcap']:,.0f}\n"
            f"🎯 Target 2x: ${data['target_mcap']:,.0f}\n"
            f"🔗 {mint[:20]}...\n\n"
        )
    await update.message.reply_text(msg)

async def scan_tokens(chat_id, app):
    global scan_active, tracked_tokens
    seen_mints = set()

    await app.bot.send_message(chat_id,
        "🔍 Scanning dimulai!\n"
        f"Filter: MCap < $50,000\n"
        f"Buy: {buy_amount} SOL | TP: 2x"
    )

    while scan_active:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://frontend-api.pump.fun/coins/latest",
                    params={"limit": 10, "includeNsfw": "false"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        coins = await resp.json()
                        for coin in coins:
                            mint = coin.get("mint", "")
                            if mint in seen_mints:
                                continue

                            name = coin.get("name", "Unknown")
                            symbol = coin.get("symbol", "???")
                            mcap = coin.get("usd_market_cap", 0)
                            replies = coin.get("reply_count", 0)
                            nsfw = coin.get("nsfw", True)

                            if nsfw:
                                continue
                            if not mcap or mcap > max_mcap:
                                continue

                            seen_mints.add(mint)
                            target_mcap = mcap * 2

                            tracked_tokens[mint] = {
                                "name": name,
                                "symbol": symbol,
                                "buy_mcap": mcap,
                                "target_mcap": target_mcap,
                            }

                            msg = (
                                f"🎯 TOKEN DITEMUKAN!\n\n"
                                f"📛 {name} (${symbol})\n"
                                f"💰 MCap: ${mcap:,.0f}\n"
                                f"💬 Replies: {replies}\n"
                                f"🎯 Target 2x: ${target_mcap:,.0f}\n"
                                f"⚡ Simulasi buy {buy_amount} SOL\n"
                                f"🔗 pump.fun/{mint}"
                            )
                            await app.bot.send_message(chat_id, msg)

        except Exception as e:
            logging.error(f"Scan error: {e}")

        await asyncio.sleep(10)

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    if scan_active:
        await update.message.reply_text("⚠️ Scan sudah berjalan!")
        return
    scan_active = True
    chat_id = update.effective_chat.id
    asyncio.create_task(scan_tokens(chat_id, context.application))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - Info bot\n"
        "/scan - Mulai scan\n"
        "/stopscan - Stop scan\n"
        "/positions - Lihat posisi aktif"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("stopscan", stopscan))
    app.add_handler(CommandHandler("positions", positions))
    app.add_handler(CommandHandler("help", help_command))
    print("Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()

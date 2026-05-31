import os
import logging
import asyncio
import aiohttp
import json
import websockets
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
HELIUS_RPC = os.environ.get("HELIUS_RPC")
scan_active = False
seen = set()
current_position = None
BUY_AMOUNT = 0.2
TAKE_PROFIT = 2.0
STOP_LOSS = 0.5

async def get_dex_info(mint, session):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
            if r.status != 200:
                return None
            data = await r.json()
            pairs = data.get("pairs", [])
            if not pairs:
                return None
            for pair in pairs:
                dex = pair.get("dexId", "")
                mcap = float(pair.get("marketCap", 0) or 0)
                liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)
                buys = pair.get("txns", {}).get("m5", {}).get("buys", 0)
                sells = pair.get("txns", {}).get("m5", {}).get("sells", 0)
                change5m = float(pair.get("priceChange", {}).get("m5", 0) or 0)
                change1h = float(pair.get("priceChange", {}).get("h1", 0) or 0)
                volume5m = float(pair.get("volume", {}).get("m5", 0) or 0)
                if dex not in ["raydium", "pumpswap"]:
                    continue
                if mcap < 20000 or mcap > 150000:
                    continue
                if liquidity < 5000:
                    continue
                return {
                    "mcap": mcap,
                    "liquidity": liquidity,
                    "buys": buys,
                    "sells": sells,
                    "change5m": change5m,
                    "change1h": change1h,
                    "volume5m": volume5m,
                    "dex": dex,
                }
        return None
    except Exception as e:
        logging.error(f"DexScreener error: {e}")
        return None

async def monitor_and_exit(mint, name, buy_mcap, chat_id, app):
    global current_position
    async with aiohttp.ClientSession() as session:
        while current_position:
            await asyncio.sleep(10)
            try:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status != 200:
                        continue
                    data = await r.json()
                    pairs = data.get("pairs", [])
                    if not pairs:
                        continue
                    current_mcap = float(pairs[0].get("marketCap", 0) or 0)
                    if not current_mcap:
                        continue
                    change = current_mcap / buy_mcap
                    pct = (change - 1) * 100
                    if change >= TAKE_PROFIT:
                        await app.bot.send_message(chat_id,
                            f"TAKE PROFIT!\n"
                            f"{name}\n"
                            f"Buy MCap: ${buy_mcap:,.0f}\n"
                            f"Sell MCap: ${current_mcap:,.0f}\n"
                            f"Profit: +{pct:.1f}%\n"
                            f"Est: +{BUY_AMOUNT*(change-1):.3f} SOL\n\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
                    elif change <= STOP_LOSS:
                        await app.bot.send_message(chat_id,
                            f"STOP LOSS!\n"
                            f"{name}\n"
                            f"Buy MCap: ${buy_mcap:,.0f}\n"
                            f"Sell MCap: ${current_mcap:,.0f}\n"
                            f"Loss: {pct:.1f}%\n\n"
                            f"Mencari token berikutnya..."
                        )
                        current_position = None
                        break
            except Exception as e:
                logging.error(e)

async def scan_tokens(chat_id, app):
    global scan_active, seen, current_position
    await app.bot.send_message(chat_id,
        "Scanner aktif!\n"
        "WebSocket + Helius RPC\n"
        "Filter: Raydium/PumpSwap MCap $20k-$150k"
    )

    uri = "wss://pumpportal.fun/api/data"

    while scan_active:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                await app.bot.send_message(chat_id, "Terhubung ke Pump.fun!")

                async with aiohttp.ClientSession() as session:
                    while scan_active:
                        if current_position:
                            await asyncio.sleep(3)
                            continue
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            data = json.loads(msg)
                            mint = data.get("mint", "")
                            if not mint or mint in seen:
                                continue
                            seen.add(mint)
                            name = data.get("name", "Unknown")
                            symbol = data.get("symbol", "???")
                            twitter = data.get("twitter", "")
                            website = data.get("website", "")

                            await asyncio.sleep(30)

                            info = await get_dex_info(mint, session)
                            if not info:
                                continue

                            current_position = {
                                "mint": mint,
                                "name": name,
                                "buy_mcap": info["mcap"],
                            }

                            await app.bot.send_message(chat_id,
                                f"TOKEN DITEMUKAN!\n\n"
                                f"{name} ({symbol})\n"
                                f"DEX: {info['dex']}\n"
                                f"Buy MCap: ${info['mcap']:,.0f}\n"
                                f"Target 2x: ${info['mcap']*2:,.0f}\n"
                                f"Stop loss: ${info['mcap']*0.5:,.0f}\n"
                                f"Liquidity: ${info['liquidity']:,.0f}\n"
                                f"Volume 5m: ${info['volume5m']:,.0f}\n"
                                f"Pump 5m: {info['change5m']:.1f}%\n"
                                f"Pump 1h: {info['change1h']:.1f}%\n"
                                f"Buy/Sell: {info['buys']}/{info['sells']}\n"
                                f"Twitter: {twitter if twitter else 'Tidak ada'}\n"
                                f"Website: {website if website else 'Tidak ada'}\n"
                                f"CA: {mint}\n\n"
                                f"Simulasi buy {BUY_AMOUNT} SOL\n"
                                f"dexscreener.com/solana/{mint}"
                            )
                            asyncio.create_task(
                                monitor_and_exit(mint, name, info["mcap"], chat_id, app)
                            )

                        except asyncio.TimeoutError:
                            continue
                        except Exception as e:
                            logging.error(e)

        except Exception as e:
            logging.error(f"WS error: {e}")
            if scan_active:
                await app.bot.send_message(chat_id, "Reconnecting...")
                await asyncio.sleep(5)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status = f"Posisi: {current_position['name']}" if current_position else "Tidak ada posisi"
    await update.message.reply_text(
        f"Pumpfun Bot v2\n\n"
        f"Buy: {BUY_AMOUNT} SOL\n"
        f"Take Profit: {TAKE_PROFIT}x\n"
        f"Stop Loss: {int(STOP_LOSS*100)}%\n"
        f"RPC: Helius\n"
        f"{status}\n\n"
        "/scan - Mulai\n"
        "/stopscan - Stop\n"
        "/status - Cek posisi"
    )

async def stopscan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    scan_active = False
    await update.message.reply_text("Stop!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not current_position:
        await update.message.reply_text("Tidak ada posisi aktif.")
        return
    await update.message.reply_text(
        f"Posisi Aktif:\n"
        f"{current_position['name']}\n"
        f"Buy MCap: ${current_position['buy_mcap']:,.0f}\n"
        f"Target 2x: ${current_position['buy_mcap']*2:,.0f}\n"
        f"CA: {current_position['mint']}"
    )

async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global scan_active
    if scan_active:
        await update.message.reply_text("Sudah jalan!")
        return
    scan_active = True
    asyncio.create_task(scan_tokens(update.effective_chat.id, context.application))

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("stopscan", stopscan))
    app.add_handler(CommandHandler("status", status))
    app.run_polling()

if __name__ == "__main__":
    main()

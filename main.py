import os
from datetime import datetime
import pytz
from fetch_data import get_m15_data, get_config
from strategy import check_pullback_setup, calc_lot
from ai_summary import validate_setup
from news_filter import get_upcoming_events
from telegram_send import send

WIB = pytz.timezone("Asia/Jakarta")

def scan():
    cfg = get_config()
    now = datetime.now(WIB)

    # 1. Ambil data M15
    df = get_m15_data()

    # 2. Cek setup pullback
    result = check_pullback_setup(df)

    # 3. Cek news
    news_info = {"has_high_impact": False, "events": []}
    if cfg["news"]["enabled"]:
        news_info = get_upcoming_events(
            cfg["news"]["minutes_before"],
            cfg["news"]["minutes_after"]
        )

    # Kalau ada news high impact → langsung tolak
    if news_info.get("has_high_impact"):
        ev = ", ".join([f"{e['title']} ({e['time']})" for e in news_info["events"]])
        msg = f"""🔍 *M15 SCAN — {now.strftime('%d %b %H:%M')} WIB*

❌ *NO TRADE — NEWS HIGH IMPACT*

Event: {ev}
Hindari entry 30 menit sebelum/sesudah news.

Tunggu sampai news selesai."""
        send(msg)
        print("Rejected: news")
        return

    # Kalau gak ada setup
    if not result or not result.get("valid"):
        reason = result.get("reason", "Tidak ada setup") if result else "Tidak ada setup"
        msg = f"""🔍 *M15 SCAN — {now.strftime('%d %b %H:%M')} WIB*

❌ *NO SETUP*

Alasan: {reason}

Coba lagi 15-30 menit lagi."""
        send(msg)
        print(f"No setup: {reason}")
        return

    # 4. Setup valid → minta Groq validasi
    groq = validate_setup(result, news_info)

    # 5. Hitung lot
    lot = calc_lot(cfg["equity"], cfg["risk_pct"], result["risk_pts"])

    # 6. Kirim alert lengkap
    direction_emoji = "🟢" if result["direction"] == "LONG" else "🔴"
    fib_mark = "✅" if result["fib_confluence"] else "⚠️"

    msg = f"""🚨 *M15 PULLBACK SETUP*
📅 {now.strftime('%d %b %Y %H:%M')} WIB

{direction_emoji} *{result['direction']}* (limit @ EMA20)
Trend M15: *{result['trend']}*
EMA20: {result['ema20']} | EMA50: {result['ema50']}
ATR: {result['atr']} | ADX: {result['adx']}

🎯 *ORDER*
Entry (limit): *{result['entry']}*
SL: {result['sl']} ({result['risk_pts']} pts)
TP: {result['tp']} ({result['reward_pts']} pts)
RR: *{result['rr']}*

💰 *SIZING* (equity ${cfg['equity']}, risk {cfg['risk_pct']}%)
Lot: *{lot}*
Risk: ${cfg['equity'] * cfg['risk_pct'] / 100:.2f}

📐 *FIBONACCI* {fib_mark}
{result['fib_note']}
0.5: {result['fibs']['0.5']} | 0.618: {result['fibs']['0.618']}

🤖 *GROQ SCORE*: {groq['score']}/10
{groq['alasan']}
Warning: {groq['warning']}

⚠️ Cross-check level di MT5 sebelum entry."""
    send(msg)
    print(f"Setup sent: {result['direction']} @ {result['entry']}")

if __name__ == "__main__":
    mode = os.getenv("MODE", "scan")
    if mode == "scan":
        scan()
    else:
        print(f"Unknown mode: {mode}")

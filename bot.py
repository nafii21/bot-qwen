import os
from datetime import datetime
import pytz
from fetch_data import get_daily_context
from strategy import build_setup
from ai_summary import summarize
from telegram_send import send

WIB = pytz.timezone("Asia/Jakarta")

def run(mode):
    ctx = get_daily_context()
    setup = build_setup(ctx, mode=mode)
    narrative = summarize(ctx, setup)

    header = "🌅 *US100 PLAYBOOK PAGI*" if mode == "morning" else "🌆 *US100 UPDATE SORE*"

    msg = f"""{header}
📅 {datetime.now(WIB).strftime('%d %b %Y %H:%M')} WIB

🧭 Regime: *{ctx['regime']}*
🎯 Bias: *{ctx['bias']}*

📈 *Key Levels*
PDH: {ctx['pdh']:.1f}
PDL: {ctx['pdl']:.1f}
PDC: {ctx['pdc']:.1f}
Pivot: {ctx['pivot']:.1f}
R1: {ctx['r1']:.1f}
S1: {ctx['s1']:.1f}

📊 RSI: {ctx['rsi']:.1f} | ADX: {ctx['adx']:.1f} | ATR: {ctx['atr']:.1f}
📉 VIX: {ctx['vix']:.1f} | DXY: {ctx['dxy']:.2f} | US10Y: {ctx['tnx']:.2f}%

⚠️ {ctx['warning']}

🎯 *SETUP*
{setup['text']}

💡 {narrative}

Confidence: {setup['confidence']}/10
"""
    send(msg)
    print("Sent.")

if __name__ == "__main__":
    mode = os.getenv("MODE", "morning")
    run(mode)

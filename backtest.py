import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ============ CONFIG ============
SPREAD_POINTS = float(os.getenv("BT_SPREAD", "2.0"))
SLIPPAGE_POINTS = float(os.getenv("BT_SLIPPAGE", "1.0"))
RISK_PCT = float(os.getenv("BT_RISK", "0.5"))
INITIAL_EQUITY = float(os.getenv("BT_EQUITY", "1000"))
RR_TARGET = 1.5
EMA_FAST = 20
EMA_SLOW = 50
ATR_PERIOD = 14
ADX_PERIOD = 14
ADX_MIN = 20
SWING_LOOKBACK = 30
MAX_DIST_ATR = 1.5
MAX_HOLD_CANDLES = 32   # 32 x M15 = 8 jam
COST = SPREAD_POINTS + SLIPPAGE_POINTS

# ============ INDIKATOR ============
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff(); dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.rolling(n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(n).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(n).mean() / atr_
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(n).mean()

# ============ FETCH ============
def fetch_m15():
    """Ambil M15 max 60 hari (limit yfinance)."""
    print("Fetching M15 data (max 60 days)...")
    df = yf.download("^NDX", period="60d", interval="15m",
                     auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    df["EMA20"] = ema(df["Close"], EMA_FAST)
    df["EMA50"] = ema(df["Close"], EMA_SLOW)
    df["ATR14"] = atr(df, ATR_PERIOD)
    df["ADX14"] = adx(df, ADX_PERIOD)
    return df.dropna()

# ============ SIMULASI TRADE ============
def simulate(df, i, direction, entry, sl, tp):
    """Cek candle-candle berikutnya: TP atau SL dulu?"""
    half_cost = COST / 2

    if direction == "LONG":
        entry_eff = entry + half_cost
        sl_eff = sl - half_cost
        tp_eff = tp - half_cost
        risk = entry_eff - sl_eff
        if risk <= 0: return None

        for j in range(i + 1, min(i + 1 + MAX_HOLD_CANDLES, len(df))):
            c = df.iloc[j]
            # Cek SL dulu (konservatif)
            if c["Low"] <= sl_eff:
                return {"result": "LOSS", "R": -1.0, "exit_idx": j - i}
            if c["High"] >= tp_eff:
                return {"result": "WIN", "R": RR_TARGET, "exit_idx": j - i}

        # Timeout
        exit_idx = min(i + MAX_HOLD_CANDLES, len(df) - 1)
        exit_p = df.iloc[exit_idx]["Close"]
        r = (exit_p - entry_eff) / risk
        return {"result": "TIMEOUT", "R": r, "exit_idx": MAX_HOLD_CANDLES}

    else:  # SHORT
        entry_eff = entry - half_cost
        sl_eff = sl + half_cost
        tp_eff = tp + half_cost
        risk = sl_eff - entry_eff
        if risk <= 0: return None

        for j in range(i + 1, min(i + 1 + MAX_HOLD_CANDLES, len(df))):
            c = df.iloc[j]
            if c["High"] >= sl_eff:
                return {"result": "LOSS", "R": -1.0, "exit_idx": j - i}
            if c["Low"] <= tp_eff:
                return {"result": "WIN", "R": RR_TARGET, "exit_idx": j - i}

        exit_idx = min(i + MAX_HOLD_CANDLES, len(df) - 1)
        exit_p = df.iloc[exit_idx]["Close"]
        r = (entry_eff - exit_p) / risk
        return {"result": "TIMEOUT", "R": r, "exit_idx": MAX_HOLD_CANDLES}

# ============ CEK SETUP ============
def check_setup(df, i):
    if i < SWING_LOOKBACK + 5:
        return None

    last = df.iloc[i]
    prev = df.iloc[i - 1]

    close = float(last["Close"])
    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    atr_v = float(last["ATR14"])
    adx_v = float(last["ADX14"]) if not pd.isna(last["ADX14"]) else 0

    if adx_v < ADX_MIN:
        return None

    dist = abs(close - ema20)
    if dist > MAX_DIST_ATR * atr_v:
        return None

    # LONG
    if ema20 > ema50 and close > ema50:
        touched = (prev["Low"] <= ema20 * 1.002 or prev["Low"] <= ema50 * 1.002)
        confirm = close > ema20 and close > prev["Close"]
        if not (touched and confirm):
            return None

        recent = df.iloc[max(0, i - SWING_LOOKBACK):i + 1]
        swing_low = float(recent["Low"].min())
        sl = swing_low - 0.2 * atr_v
        entry = ema20
        risk = entry - sl
        if risk <= 0 or risk > 3 * atr_v:
            return None
        tp = entry + RR_TARGET * risk
        return {"direction": "LONG", "entry": entry, "sl": sl, "tp": tp,
                "risk_pts": risk}

    # SHORT
    if ema20 < ema50 and close < ema50:
        touched = (prev["High"] >= ema20 * 0.998 or prev["High"] >= ema50 * 0.998)
        confirm = close < ema20 and close < prev["Close"]
        if not (touched and confirm):
            return None

        recent = df.iloc[max(0, i - SWING_LOOKBACK):i + 1]
        swing_high = float(recent["High"].max())
        sl = swing_high + 0.2 * atr_v
        entry = ema20
        risk = sl - entry
        if risk <= 0 or risk > 3 * atr_v:
            return None
        tp = entry - RR_TARGET * risk
        return {"direction": "SHORT", "entry": entry, "sl": sl, "tp": tp,
                "risk_pts": risk}

    return None

# ============ MAIN BACKTEST ============
def run_backtest():
    df = fetch_m15()
    print(f"Data loaded: {len(df)} candles")
    print(f"Period: {df.index[0]} → {df.index[-1]}")

    trades = []
    i = SWING_LOOKBACK + 5
    while i < len(df) - MAX_HOLD_CANDLES - 1:
        sig = check_setup(df, i)
        if sig:
            sim = simulate(df, i, sig["direction"], sig["entry"], sig["sl"], sig["tp"])
            if sim:
                trades.append({
                    "datetime": str(df.index[i]),
                    "direction": sig["direction"],
                    "entry": round(sig["entry"], 1),
                    "sl": round(sig["sl"], 1),
                    "tp": round(sig["tp"], 1),
                    "risk_pts": round(sig["risk_pts"], 1),
                    **sim
                })
                # Skip beberapa candle biar gak overlap
                i += sim["exit_idx"] + 1
                continue
        i += 1

    return pd.DataFrame(trades)

# ============ METRIK ============
def calc_metrics(tdf):
    if len(tdf) == 0:
        return "No trades triggered."

    wins = tdf[tdf["R"] > 0]
    losses = tdf[tdf["R"] < 0]
    timeouts = tdf[tdf["result"] == "TIMEOUT"]

    total_r = tdf["R"].sum()
    win_rate = len(wins) / len(tdf) * 100
    gross_win = wins["R"].sum() if len(wins) else 0
    gross_loss = abs(losses["R"].sum()) if len(losses) else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_r = tdf["R"].mean()

    # Equity curve
    equity = INITIAL_EQUITY
    peak = equity
    max_dd = 0
    for _, t in tdf.iterrows():
        risk_usd = equity * RISK_PCT / 100
        equity += risk_usd * t["R"]
        if equity > peak: peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd: max_dd = dd

    # Streaks
    max_w = 0; max_l = 0; cw = 0; cl = 0
    for _, t in tdf.iterrows():
        if t["R"] > 0: cw += 1; cl = 0; max_w = max(max_w, cw)
        elif t["R"] < 0: cl += 1; cw = 0; max_l = max(max_l, cl)
        else: cw = 0; cl = 0

    # LONG vs SHORT
    longs = tdf[tdf["direction"] == "LONG"]
    shorts = tdf[tdf["direction"] == "SHORT"]

    r = []
    r.append("=" * 55)
    r.append("  M15 PULLBACK BACKTEST RESULT")
    r.append("=" * 55)
    r.append(f"Period          : {tdf['datetime'].iloc[0]} → {tdf['datetime'].iloc[-1]}")
    r.append(f"Risk / trade    : {RISK_PCT}%")
    r.append(f"Initial equity  : ${INITIAL_EQUITY:,.0f}")
    r.append(f"Biaya / trade   : {COST:.1f} poin")
    r.append(f"RR Target       : 1:{RR_TARGET}")
    r.append("-" * 55)
    r.append(f"Total trades    : {len(tdf)}")
    r.append(f"  Wins          : {len(wins)}")
    r.append(f"  Losses        : {len(losses)}")
    r.append(f"  Timeouts      : {len(timeouts)}")
    r.append(f"Win rate        : {win_rate:.1f}%")
    r.append("-" * 55)
    r.append(f"Total R         : {total_r:+.2f}")
    r.append(f"Avg R / trade   : {avg_r:+.3f}")
    r.append(f"Profit Factor   : {pf:.2f}")
    r.append("-" * 55)
    r.append(f"Final equity    : ${equity:,.2f}")
    r.append(f"Total return    : {(equity - INITIAL_EQUITY)/INITIAL_EQUITY*100:+.1f}%")
    r.append(f"Max drawdown    : {max_dd:.1f}%")
    r.append(f"Max win streak  : {max_w}")
    r.append(f"Max loss streak : {max_l}")
    r.append("-" * 55)
    r.append(f"LONG            : {len(longs)} trades, {longs['R'].sum():+.2f}R, "
             f"win {(longs['R'] > 0).mean()*100:.1f}%")
    r.append(f"SHORT           : {len(shorts)} trades, {shorts['R'].sum():+.2f}R, "
             f"win {(shorts['R'] > 0).mean()*100:.1f}%")
    r.append("=" * 55)
    r.append("LAST 15 TRADES")
    r.append("-" * 55)
    r.append(tdf.tail(15).to_string(index=False))
    r.append("=" * 55)

    # Verdict
    r.append("")
    if len(tdf) < 30:
        r.append("⚠️  SAMPLE KECIL: < 30 trade, hasil belum valid secara statistik")
    if pf >= 1.5:
        r.append("✅ VERDICT: LAYAK")
    elif pf >= 1.3:
        r.append("⚠️  VERDICT: OK, perlu optimasi")
    elif pf >= 1.0:
        r.append("⚠️  VERDICT: Marginal")
    else:
        r.append("❌ VERDICT: JANGAN LIVE")

    return "\n".join(r)

# ============ TELEGRAM ============
def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("(Telegram skip)")
        return
    max_len = 3800
    for i in range(0, len(text), max_len):
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": f"```\n{text[i:i+max_len]}\n```",
                      "parse_mode": "Markdown"},
                timeout=30
            )
        except Exception as e:
            print(f"Telegram err: {e}")

# ============ RUN ============
if __name__ == "__main__":
    print("Starting M15 pullback backtest...")
    tdf = run_backtest()
    report = calc_metrics(tdf)
    print(report)
    if len(tdf) > 0:
        tdf.to_csv("backtest_m15.csv", index=False)
        print("\n📁 backtest_m15.csv saved")
    send_telegram(report)

import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ============ CONFIG ============
START_DATE = os.getenv("BT_START", "2015-01-01")
END_DATE = os.getenv("BT_END", datetime.now().strftime("%Y-%m-%d"))
SPREAD_POINTS = float(os.getenv("BT_SPREAD", "2.0"))     # spread USTEC Exness
SLIPPAGE_POINTS = float(os.getenv("BT_SLIPPAGE", "1.0")) # slippage rata-rata
RISK_PCT = float(os.getenv("BT_RISK", "0.5"))            # risk per trade %
INITIAL_EQUITY = float(os.getenv("BT_EQUITY", "10000"))
MAX_HOLD_DAYS = 5                                        # max hold dalam hari
COST_PER_TRADE = SPREAD_POINTS + SLIPPAGE_POINTS         # total biaya per round trip

# ============ INDIKATOR ============
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = -d.clip(upper=0).rolling(n).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def adx(df, n=14):
    h, l, c = df["High"], df["Low"], df["Close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr_ = tr.rolling(n).mean()
    plus_di = 100 * pd.Series(plus_dm, index=df.index).rolling(n).mean() / atr_
    minus_di = 100 * pd.Series(minus_dm, index=df.index).rolling(n).mean() / atr_
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.rolling(n).mean()

# ============ FETCH DATA ============
def fetch_data():
    print(f"Fetching ^NDX from {START_DATE} to {END_DATE}...")
    df = yf.download("^NDX", start=START_DATE, end=END_DATE,
                     interval="1d", auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    df["EMA20"]  = ema(df["Close"], 20)
    df["EMA50"]  = ema(df["Close"], 50)
    df["EMA200"] = ema(df["Close"], 200)
    df["RSI14"]  = rsi(df["Close"], 14)
    df["ATR14"]  = atr(df, 14)
    df["ADX14"]  = adx(df, 14)
    return df.dropna()

# ============ LOGIKA SETUP ============
def check_pullback_long(row, prev):
    """Model A — Pullback Long"""
    if (row["Close"] > row["EMA200"]
        and row["EMA50"] > row["EMA200"]
        and 40 <= row["RSI14"] <= 60
        and row["Close"] > prev["High"]):
        return True
    return False

def check_pullback_short(row, prev):
    """Model A — Pullback Short"""
    if (row["Close"] < row["EMA200"]
        and row["EMA50"] < row["EMA200"]
        and 40 <= row["RSI14"] <= 60
        and row["Close"] < prev["Low"]):
        return True
    return False

# ============ SIMULASI 1 TRADE ============
def simulate_trade(df, i, direction, entry_price, sl, tp, risk):
    """Cek hari-hari berikutnya, lihat TP atau SL kena dulu."""
    # Biaya masuk (setengah spread + slippage)
    half_cost = COST_PER_TRADE / 2

    if direction == "LONG":
        entry = entry_price + half_cost
        sl_eff = sl - half_cost
        tp_eff = tp - half_cost
        risk_eff = entry - sl_eff

        for j in range(i + 1, min(i + 1 + MAX_HOLD_DAYS, len(df))):
            day = df.iloc[j]
            # Cek SL dulu (konservatif)
            if day["Low"] <= sl_eff:
                return {"result": "LOSS", "R": -1.0, "exit_day": j - i,
                        "exit_price": sl_eff}
            if day["High"] >= tp_eff:
                r = (tp_eff - entry) / risk_eff
                return {"result": "WIN", "R": r, "exit_day": j - i,
                        "exit_price": tp_eff}

        # Timeout
        exit_day_idx = min(i + MAX_HOLD_DAYS, len(df) - 1)
        exit_p = df.iloc[exit_day_idx]["Close"]
        r = (exit_p - entry) / risk_eff
        return {"result": "TIMEOUT", "R": r, "exit_day": MAX_HOLD_DAYS,
                "exit_price": exit_p}

    else:  # SHORT
        entry = entry_price - half_cost
        sl_eff = sl + half_cost
        tp_eff = tp + half_cost
        risk_eff = sl_eff - entry

        for j in range(i + 1, min(i + 1 + MAX_HOLD_DAYS, len(df))):
            day = df.iloc[j]
            if day["High"] >= sl_eff:
                return {"result": "LOSS", "R": -1.0, "exit_day": j - i,
                        "exit_price": sl_eff}
            if day["Low"] <= tp_eff:
                r = (entry - tp_eff) / risk_eff
                return {"result": "WIN", "R": r, "exit_day": j - i,
                        "exit_price": tp_eff}

        exit_day_idx = min(i + MAX_HOLD_DAYS, len(df) - 1)
        exit_p = df.iloc[exit_day_idx]["Close"]
        r = (entry - exit_p) / risk_eff
        return {"result": "TIMEOUT", "R": r, "exit_day": MAX_HOLD_DAYS,
                "exit_price": exit_p}

# ============ MAIN BACKTEST ============
def run_backtest():
    df = fetch_data()
    print(f"Data loaded: {len(df)} candles")

    trades = []

    for i in range(200, len(df) - MAX_HOLD_DAYS - 1):
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        atr = row["ATR14"]

        # ===== Model A — Pullback Long =====
        if check_pullback_long(row, prev):
            entry = row["Close"]
            sl = min(row["Low"], row["EMA50"]) - atr * 0.5
            risk = entry - sl
            if risk <= 0 or risk > atr * 3:
                continue
            tp = entry + 1.5 * risk

            sim = simulate_trade(df, i, "LONG", entry, sl, tp, risk)
            trades.append({
                "date": str(row.name)[:10],
                "model": "A_LONG",
                "entry": round(entry, 1),
                "sl": round(sl, 1),
                "tp": round(tp, 1),
                **sim
            })
            continue

        # ===== Model A — Pullback Short =====
        if check_pullback_short(row, prev):
            entry = row["Close"]
            sl = max(row["High"], row["EMA50"]) + atr * 0.5
            risk = sl - entry
            if risk <= 0 or risk > atr * 3:
                continue
            tp = entry - 1.5 * risk

            sim = simulate_trade(df, i, "SHORT", entry, sl, tp, risk)
            trades.append({
                "date": str(row.name)[:10],
                "model": "A_SHORT",
                "entry": round(entry, 1),
                "sl": round(sl, 1),
                "tp": round(tp, 1),
                **sim
            })

    return pd.DataFrame(trades)

# ============ METRIK ============
def calc_metrics(tdf):
    if len(tdf) == 0:
        return "No trades triggered in this period."

    wins = tdf[tdf["R"] > 0]
    losses = tdf[tdf["R"] < 0]
    timeouts = tdf[tdf["result"] == "TIMEOUT"]

    total_r = tdf["R"].sum()
    win_rate = len(wins) / len(tdf) * 100
    gross_win = wins["R"].sum() if len(wins) else 0
    gross_loss = abs(losses["R"].sum()) if len(losses) else 0
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    avg_r = tdf["R"].mean()
    avg_win = wins["R"].mean() if len(wins) else 0
    avg_loss = losses["R"].mean() if len(losses) else 0

    # Equity curve + max drawdown
    equity = INITIAL_EQUITY
    peak = equity
    max_dd = 0
    max_dd_start = None
    max_dd_end = None
    cur_dd_start = None
    for _, t in tdf.iterrows():
        risk_amount = equity * RISK_PCT / 100
        equity += risk_amount * t["R"]
        if equity > peak:
            peak = equity
            cur_dd_start = None
        else:
            if cur_dd_start is None:
                cur_dd_start = t["date"]
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
                max_dd_start = cur_dd_start
                max_dd_end = t["date"]

    # Streak
    max_win_streak = 0
    max_loss_streak = 0
    cur_w = 0
    cur_l = 0
    for _, t in tdf.iterrows():
        if t["R"] > 0:
            cur_w += 1
            cur_l = 0
            max_win_streak = max(max_win_streak, cur_w)
        elif t["R"] < 0:
            cur_l += 1
            cur_w = 0
            max_loss_streak = max(max_loss_streak, cur_l)
        else:
            cur_w = 0
            cur_l = 0

    # Yearly breakdown
    tdf["year"] = tdf["date"].str[:4]
    yearly = tdf.groupby("year").agg(
        trades=("R", "count"),
        total_r=("R", "sum"),
        win_rate=("R", lambda x: (x > 0).mean() * 100)
    ).round(2)

    report = []
    report.append("=" * 50)
    report.append("  US100 BACKTEST RESULT")
    report.append("=" * 50)
    report.append(f"Period          : {tdf['date'].iloc[0]} → {tdf['date'].iloc[-1]}")
    report.append(f"Risk / trade    : {RISK_PCT}%")
    report.append(f"Initial equity  : ${INITIAL_EQUITY:,.0f}")
    report.append(f"Biaya / trade   : {COST_PER_TRADE:.1f} poin (spread+slip)")
    report.append("-" * 50)
    report.append(f"Total trades    : {len(tdf)}")
    report.append(f"  Wins          : {len(wins)}")
    report.append(f"  Losses        : {len(losses)}")
    report.append(f"  Timeouts      : {len(timeouts)}")
    report.append(f"Win rate        : {win_rate:.1f}%")
    report.append(f"Avg win         : {avg_win:+.2f} R")
    report.append(f"Avg loss        : {avg_loss:+.2f} R")
    report.append("-" * 50)
    report.append(f"Total R         : {total_r:+.2f}")
    report.append(f"Avg R / trade   : {avg_r:+.3f}")
    report.append(f"Profit Factor   : {pf:.2f}")
    report.append(f"Expectancy      : {avg_r:+.3f} R")
    report.append("-" * 50)
    report.append(f"Final equity    : ${equity:,.2f}")
    report.append(f"Total return    : {(equity - INITIAL_EQUITY)/INITIAL_EQUITY*100:+.1f}%")
    report.append(f"Max drawdown    : {max_dd:.1f}%")
    if max_dd_start:
        report.append(f"  DD period     : {max_dd_start} → {max_dd_end}")
    report.append(f"Max win streak  : {max_win_streak}")
    report.append(f"Max loss streak : {max_loss_streak}")
    report.append("-" * 50)
    report.append("")
    report.append("YEARLY BREAKDOWN")
    report.append("-" * 50)
    report.append(yearly.to_string())
    report.append("")
    report.append("=" * 50)
    report.append("LAST 10 TRADES")
    report.append("-" * 50)
    report.append(tdf.tail(10).to_string(index=False))
    report.append("=" * 50)

    # Verdict
    report.append("")
    if pf >= 1.5:
        report.append("✅ VERDICT: Strategi LAYAK dipakai (PF >= 1.5)")
    elif pf >= 1.3:
        report.append("⚠️  VERDICT: Strategi OK tapi perlu optimasi (PF 1.3-1.5)")
    elif pf >= 1.0:
        report.append("⚠️  VERDICT: Marginal, jangan naikin lot dulu (PF 1.0-1.3)")
    else:
        report.append("❌ VERDICT: JANGAN live trading. Strategi rugi (PF < 1.0)")

    return "\n".join(report)

# ============ KIRIM TELEGRAM (OPSIONAL) ============
def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("(Telegram skip: token/chat_id tidak ada)")
        return
    # Telegram max 4096 char per message
    max_len = 4000
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": f"```\n{chunk}\n```",
                      "parse_mode": "Markdown"},
                timeout=30
            )
        except Exception as e:
            print(f"Telegram error: {e}")

# ============ RUN ============
if __name__ == "__main__":
    print("=" * 50)
    print("Starting backtest...")
    print("=" * 50)

    tdf = run_backtest()
    report = calc_metrics(tdf)

    print(report)

    # Simpan CSV juga
    if len(tdf) > 0:
        tdf.to_csv("backtest_trades.csv", index=False)
        print("\n📁 Trade list saved to backtest_trades.csv")

    send_telegram(report)

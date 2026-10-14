import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# ============ CONFIG ============
START_DATE = os.getenv("BT_START", "2015-01-01")
END_DATE = os.getenv("BT_END", datetime.now().strftime("%Y-%m-%d"))
SPREAD_POINTS = float(os.getenv("BT_SPREAD", "2.0"))
SLIPPAGE_POINTS = float(os.getenv("BT_SLIPPAGE", "1.0"))
RISK_PCT = float(os.getenv("BT_RISK", "0.5"))
INITIAL_EQUITY = float(os.getenv("BT_EQUITY", "10000"))
MAX_HOLD_DAYS = 5
COST_PER_TRADE = SPREAD_POINTS + SLIPPAGE_POINTS

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

# ============ SIMULASI 1 TRADE ============
def simulate_trade(df, signal_idx, direction, entry, sl, tp1, tp2):
    """
    Simulasi trade dari signal_idx + 1 sampai MAX_HOLD_DAYS.
    Aturan: 50% TP1, 50% TP2.
    Kalau TP1 kena → SL geser ke breakeven (live bot rule).
    """
    half_cost = COST_PER_TRADE / 2

    if direction == "LONG":
        entry_eff = entry + half_cost
        sl_eff = sl - half_cost
        tp1_eff = tp1 - half_cost
        tp2_eff = tp2 - half_cost
        risk = entry_eff - sl_eff
        if risk <= 0: return None

        tp1_hit = False
        for j in range(signal_idx + 1, min(signal_idx + 1 + MAX_HOLD_DAYS, len(df))):
            day = df.iloc[j]

            # Cek SL dulu (konservatif)
            # Kalau TP1 udah kena, SL = entry (breakeven)
            sl_now = entry_eff if tp1_hit else sl_eff
            if day["Low"] <= sl_now:
                if tp1_hit:
                    # 50% TP1 (+1.5R) + 50% breakeven (0R) = +0.75R total
                    return {"result": "WIN_PARTIAL", "R": 0.75,
                            "exit_day": j - signal_idx}
                return {"result": "LOSS", "R": -1.0, "exit_day": j - signal_idx}

            if not tp1_hit and day["High"] >= tp1_eff:
                tp1_hit = True

            if tp1_hit and day["High"] >= tp2_eff:
                # 50% TP1 (+1.5R) + 50% TP2 (+2.5R) = +2.0R total
                return {"result": "WIN_FULL", "R": 2.0, "exit_day": j - signal_idx}

        # Timeout
        exit_idx = min(signal_idx + MAX_HOLD_DAYS, len(df) - 1)
        exit_p = df.iloc[exit_idx]["Close"]
        r_rem = (exit_p - entry_eff) / risk
        if tp1_hit:
            r_total = 0.5 * 1.5 + 0.5 * r_rem
        else:
            r_total = r_rem
        return {"result": "TIMEOUT", "R": r_total, "exit_day": MAX_HOLD_DAYS}

    else:  # SHORT
        entry_eff = entry - half_cost
        sl_eff = sl + half_cost
        tp1_eff = tp1 + half_cost
        tp2_eff = tp2 + half_cost
        risk = sl_eff - entry_eff
        if risk <= 0: return None

        tp1_hit = False
        for j in range(signal_idx + 1, min(signal_idx + 1 + MAX_HOLD_DAYS, len(df))):
            day = df.iloc[j]
            sl_now = entry_eff if tp1_hit else sl_eff

            if day["High"] >= sl_now:
                if tp1_hit:
                    return {"result": "WIN_PARTIAL", "R": 0.75,
                            "exit_day": j - signal_idx}
                return {"result": "LOSS", "R": -1.0, "exit_day": j - signal_idx}

            if not tp1_hit and day["Low"] <= tp1_eff:
                tp1_hit = True

            if tp1_hit and day["Low"] <= tp2_eff:
                return {"result": "WIN_FULL", "R": 2.0, "exit_day": j - signal_idx}

        exit_idx = min(signal_idx + MAX_HOLD_DAYS, len(df) - 1)
        exit_p = df.iloc[exit_idx]["Close"]
        r_rem = (entry_eff - exit_p) / risk
        if tp1_hit:
            r_total = 0.5 * 1.5 + 0.5 * r_rem
        else:
            r_total = r_rem
        return {"result": "TIMEOUT", "R": r_total, "exit_day": MAX_HOLD_DAYS}

# ============ MODEL A: PULLBACK KE PDC ============
def model_a_pullback(df, i):
    """Entry di PDC hari ini, based on sinyal dari prev day."""
    prev = df.iloc[i - 1]
    today = df.iloc[i]

    close_prev = prev["Close"]
    pdc = prev["Close"]
    pdh = prev["High"]
    pdl = prev["Low"]
    atr = prev["ATR14"]
    rsi_v = prev["RSI14"]
    adx_v = prev["ADX14"]
    ema50 = prev["EMA50"]
    ema200 = prev["EMA200"]

    # Regime filter
    if adx_v < 20:
        return None

    # === TREND UP → Pullback Long ===
    if close_prev > ema200 and ema50 > ema200:
        if not (40 <= rsi_v <= 60):
            return None
        # Cek: hari ini harga nyentuh PDC (pullback ke PDC)?
        if not (today["Low"] <= pdc <= today["High"]):
            return None
        entry = pdc
        sl = pdl - atr * 0.5
        risk = entry - sl
        if risk <= 0 or risk > atr * 2:
            return None
        tp1 = entry + 1.5 * risk
        tp2 = entry + 2.5 * risk
        return {"direction": "LONG", "entry": entry, "sl": sl,
                "tp1": tp1, "tp2": tp2, "model": "A_LONG"}

    # === TREND DOWN → Pullback Short ===
    if close_prev < ema200 and ema50 < ema200:
        if not (40 <= rsi_v <= 60):
            return None
        if not (today["Low"] <= pdc <= today["High"]):
            return None
        entry = pdc
        sl = pdh + atr * 0.5
        risk = sl - entry
        if risk <= 0 or risk > atr * 2:
            return None
        tp1 = entry - 1.5 * risk
        tp2 = entry - 2.5 * risk
        return {"direction": "SHORT", "entry": entry, "sl": sl,
                "tp1": tp1, "tp2": tp2, "model": "A_SHORT"}

    return None

# ============ MODEL B: ORB BREAKOUT PDH/PDL ============
def model_b_orb(df, i):
    """ORB: break PDH (uptrend) atau PDL (downtrend)."""
    prev = df.iloc[i - 1]
    today = df.iloc[i]

    close_prev = prev["Close"]
    pdh = prev["High"]
    pdl = prev["Low"]
    pdc = prev["Close"]
    atr = prev["ATR14"]
    adx_v = prev["ADX14"]
    ema50 = prev["EMA50"]
    ema200 = prev["EMA200"]

    # Pivot & R1/S1
    pivot = (pdh + pdl + pdc) / 3
    r1 = 2 * pivot - pdl
    s1 = 2 * pivot - pdh

    if adx_v < 20:
        return None

    # === TREND UP → Breakout Long ===
    if close_prev > ema200 and ema50 > ema200:
        if today["High"] >= pdh:
            entry = pdh
            sl = pdc
            risk = entry - sl
            if risk <= 0 or risk > atr * 2:
                return None
            tp1 = r1
            tp2 = pdh + atr
            if tp1 <= entry:  # TP harus di atas entry
                tp1 = entry + 1.5 * risk
            return {"direction": "LONG", "entry": entry, "sl": sl,
                    "tp1": tp1, "tp2": tp2, "model": "B_LONG"}

    # === TREND DOWN → Breakdown Short ===
    if close_prev < ema200 and ema50 < ema200:
        if today["Low"] <= pdl:
            entry = pdl
            sl = pdc
            risk = sl - entry
            if risk <= 0 or risk > atr * 2:
                return None
            tp1 = s1
            tp2 = pdl - atr
            if tp1 >= entry:
                tp1 = entry - 1.5 * risk
            return {"direction": "SHORT", "entry": entry, "sl": sl,
                    "tp1": tp1, "tp2": tp2, "model": "B_SHORT"}

    return None

# ============ MAIN BACKTEST ============
def run_backtest():
    df = fetch_data()
    print(f"Data loaded: {len(df)} candles")

    trades = []
    for i in range(201, len(df) - MAX_HOLD_DAYS - 1):
        # Max 2 trade/hari, prioritas Model A
        signals = []

        sig_a = model_a_pullback(df, i)
        if sig_a:
            signals.append(sig_a)

        sig_b = model_b_orb(df, i)
        if sig_b:
            signals.append(sig_b)

        # Prioritas Model A, max 1 trade per hari (biar konservatif)
        # Kalau lu mau 2 trade/hari, ubah jadi signals[:2]
        selected = signals[:1]

        for sig in selected:
            sim = simulate_trade(df, i, sig["direction"],
                                 sig["entry"], sig["sl"],
                                 sig["tp1"], sig["tp2"])
            if sim is None:
                continue
            trades.append({
                "date": str(df.iloc[i].name)[:10],
                "model": sig["model"],
                "direction": sig["direction"],
                "entry": round(sig["entry"], 1),
                "sl": round(sig["sl"], 1),
                "tp1": round(sig["tp1"], 1),
                "tp2": round(sig["tp2"], 1),
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

    # Equity curve
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
    max_win_streak = 0; max_loss_streak = 0
    cur_w = 0; cur_l = 0
    for _, t in tdf.iterrows():
        if t["R"] > 0:
            cur_w += 1; cur_l = 0
            max_win_streak = max(max_win_streak, cur_w)
        elif t["R"] < 0:
            cur_l += 1; cur_w = 0
            max_loss_streak = max(max_loss_streak, cur_l)
        else:
            cur_w = 0; cur_l = 0

    # Breakdown by model
    by_model = tdf.groupby("model").agg(
        trades=("R", "count"),
        total_r=("R", "sum"),
        avg_r=("R", "mean"),
        win_rate=("R", lambda x: (x > 0).mean() * 100)
    ).round(2)

    # Yearly
    tdf_copy = tdf.copy()
    tdf_copy["year"] = tdf_copy["date"].str[:4]
    yearly = tdf_copy.groupby("year").agg(
        trades=("R", "count"),
        total_r=("R", "sum"),
        win_rate=("R", lambda x: (x > 0).mean() * 100)
    ).round(2)

    r = []
    r.append("=" * 55)
    r.append("  US100 BACKTEST — LIVE BOT MATCH")
    r.append("=" * 55)
    r.append(f"Period          : {tdf['date'].iloc[0]} → {tdf['date'].iloc[-1]}")
    r.append(f"Risk / trade    : {RISK_PCT}%")
    r.append(f"Initial equity  : ${INITIAL_EQUITY:,.0f}")
    r.append(f"Biaya / trade   : {COST_PER_TRADE:.1f} poin")
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
    if max_dd_start:
        r.append(f"  DD period     : {max_dd_start} → {max_dd_end}")
    r.append(f"Max win streak  : {max_win_streak}")
    r.append(f"Max loss streak : {max_loss_streak}")
    r.append("-" * 55)
    r.append("")
    r.append("BREAKDOWN BY MODEL")
    r.append("-" * 55)
    r.append(by_model.to_string())
    r.append("")
    r.append("YEARLY")
    r.append("-" * 55)
    r.append(yearly.to_string())
    r.append("")
    r.append("=" * 55)
    r.append("LAST 10 TRADES")
    r.append("-" * 55)
    r.append(tdf.tail(10).to_string(index=False))
    r.append("=" * 55)

    r.append("")
    if pf >= 1.5:
        r.append("✅ VERDICT: LAYAK (PF >= 1.5)")
    elif pf >= 1.3:
        r.append("⚠️  VERDICT: OK, perlu optimasi (PF 1.3-1.5)")
    elif pf >= 1.0:
        r.append("⚠️  VERDICT: Marginal (PF 1.0-1.3)")
    else:
        r.append("❌ VERDICT: JANGAN LIVE (PF < 1.0)")

    return "\n".join(r)

# ============ TELEGRAM ============
def send_telegram(text):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("(Telegram skip)")
        return
    max_len = 3800
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for c in chunks:
        try:
            requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data={"chat_id": chat_id, "text": f"```\n{c}\n```",
                      "parse_mode": "Markdown"},
                timeout=30
            )
        except Exception as e:
            print(f"Telegram err: {e}")

# ============ RUN ============
if __name__ == "__main__":
    print("Starting backtest...")
    tdf = run_backtest()
    report = calc_metrics(tdf)
    print(report)
    if len(tdf) > 0:
        tdf.to_csv("backtest_trades.csv", index=False)
        print("\n📁 backtest_trades.csv saved")
    send_telegram(report)

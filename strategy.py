import pandas as pd
from fetch_data import get_swing_high_low, get_fib_levels, get_config

def check_pullback_setup(df):
    """
    Cek setup pullback M15 + Fibonacci confluence.
    Return dict setup atau None.
    """
    cfg = get_config()
    s = cfg["strategy"]
    fib_cfg = cfg["fib"]

    if len(df) < s["swing_lookback"] + 5:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close = float(last["Close"])
    ema20 = float(last["EMA20"])
    ema50 = float(last["EMA50"])
    atr = float(last["ATR14"])
    adx = float(last["ADX14"]) if not pd.isna(last["ADX14"]) else 0

    # Filter ADX
    if adx < s["adx_min"]:
        return {"reason": f"ADX {adx:.1f} < {s['adx_min']} (sideways)", "valid": False}

    # Filter jarak ke EMA
    dist = abs(close - ema20)
    if dist > s["max_dist_from_ema_atr"] * atr:
        return {"reason": f"Harga {dist:.1f} poin dari EMA20 (max {s['max_dist_from_ema_atr']*atr:.1f})",
                "valid": False}

    # Deteksi trend
    if ema20 > ema50 and close > ema50:
        trend = "UP"
        # Pullback: candle sebelumnya nyentuh/sentuh EMA20 atau EMA50
        touched_ema = (
            prev["Low"] <= ema20 * 1.002 or
            prev["Low"] <= ema50 * 1.002
        )
        # Konfirmasi: candle terakhir close di atas EMA20
        confirm = close > ema20 and close > prev["Close"]

        if not (touched_ema and confirm):
            return {"reason": "Belum ada pullback+konfirmasi bullish M15", "valid": False}

        # SL: swing low terdekat + buffer
        _, swing_low = get_swing_high_low(df, s["swing_lookback"])
        sl = swing_low - 0.2 * atr
        entry = ema20          # limit di EMA20
        risk = entry - sl
        if risk <= 0:
            return {"reason": "Risk invalid", "valid": False}
        tp = entry + s["rr_target"] * risk

        # Fibonacci
        swing_high, swing_low_f = get_swing_high_low(df, s["swing_lookback"])
        fibs = get_fib_levels(swing_high, swing_low_f, "UP")
        fib_confluence = False
        fib_note = ""
        if fib_cfg["enabled"]:
            for k, v in fibs.items():
                if abs(v - entry) < 0.3 * atr:
                    fib_confluence = True
                    fib_note = f"Entry dekat Fib {k} ({v:.1f})"
                    break
            if not fib_confluence:
                fib_note = f"Fib retracement 0.5-0.618: {fibs['0.5']:.1f} - {fibs['0.618']:.1f}"

        return {
            "valid": True,
            "direction": "LONG",
            "trend": trend,
            "entry": round(entry, 1),
            "sl": round(sl, 1),
            "tp": round(tp, 1),
            "risk_pts": round(risk, 1),
            "reward_pts": round(s["rr_target"] * risk, 1),
            "rr": f"1:{s['rr_target']}",
            "ema20": round(ema20, 1),
            "ema50": round(ema50, 1),
            "atr": round(atr, 1),
            "adx": round(adx, 1),
            "fib_confluence": fib_confluence,
            "fib_note": fib_note,
            "fibs": {k: round(v, 1) for k, v in fibs.items()},
        }

    elif ema20 < ema50 and close < ema50:
        trend = "DOWN"
        touched_ema = (
            prev["High"] >= ema20 * 0.998 or
            prev["High"] >= ema50 * 0.998
        )
        confirm = close < ema20 and close < prev["Close"]

        if not (touched_ema and confirm):
            return {"reason": "Belum ada pullback+konfirmasi bearish M15", "valid": False}

        swing_high, _ = get_swing_high_low(df, s["swing_lookback"])
        sl = swing_high + 0.2 * atr
        entry = ema20
        risk = sl - entry
        if risk <= 0:
            return {"reason": "Risk invalid", "valid": False}
        tp = entry - s["rr_target"] * risk

        swing_high2, swing_low2 = get_swing_high_low(df, s["swing_lookback"])
        fibs = get_fib_levels(swing_high2, swing_low2, "DOWN")
        fib_confluence = False
        fib_note = ""
        if fib_cfg["enabled"]:
            for k, v in fibs.items():
                if abs(v - entry) < 0.3 * atr:
                    fib_confluence = True
                    fib_note = f"Entry dekat Fib {k} ({v:.1f})"
                    break
            if not fib_confluence:
                fib_note = f"Fib retracement 0.5-0.618: {fibs['0.5']:.1f} - {fibs['0.618']:.1f}"

        return {
            "valid": True,
            "direction": "SHORT",
            "trend": trend,
            "entry": round(entry, 1),
            "sl": round(sl, 1),
            "tp": round(tp, 1),
            "risk_pts": round(risk, 1),
            "reward_pts": round(s["rr_target"] * risk, 1),
            "rr": f"1:{s['rr_target']}",
            "ema20": round(ema20, 1),
            "ema50": round(ema50, 1),
            "atr": round(atr, 1),
            "adx": round(adx, 1),
            "fib_confluence": fib_confluence,
            "fib_note": fib_note,
            "fibs": {k: round(v, 1) for k, v in fibs.items()},
        }

    return {"reason": "EMA20 & EMA50 tidak searah (no clear trend)", "valid": False}

def calc_lot(equity, risk_pct, sl_points, point_value=1.0):
    """
    Hitung lot size.
    equity: USD
    risk_pct: % per trade
    sl_points: jarak SL dalam poin
    point_value: nilai $ per poin per 1 lot (USTEC = 1.0)
    """
    risk_usd = equity * risk_pct / 100
    if sl_points <= 0:
        return 0
    lot = risk_usd / (sl_points * point_value)
    return round(lot, 2)

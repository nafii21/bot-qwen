def build_setup(ctx, mode="morning"):
    if mode == "morning":
        return setup_pullback(ctx)
    return setup_orb(ctx)

def setup_pullback(ctx):
    if ctx["regime"] == "TREND UP":
        entry = ctx["pdc"]
        sl = ctx["pdl"] - ctx["atr"] * 0.5
        risk = entry - sl
        return {
            "text": (
                f"*Model A — Pullback Long*\n"
                f"Tunggu pullback ke {entry:.1f} + konfirmasi candle M15\n"
                f"Entry: {entry:.1f}\n"
                f"SL: {sl:.1f}\n"
                f"TP1: {entry + 1.5*risk:.1f}\n"
                f"TP2: {entry + 2.5*risk:.1f}"
            ),
            "confidence": _conf(ctx),
        }
    if ctx["regime"] == "TREND DOWN":
        entry = ctx["pdc"]
        sl = ctx["pdh"] + ctx["atr"] * 0.5
        risk = sl - entry
        return {
            "text": (
                f"*Model A — Pullback Short*\n"
                f"Tunggu rally ke {entry:.1f} + konfirmasi candle M15\n"
                f"Entry: {entry:.1f}\n"
                f"SL: {sl:.1f}\n"
                f"TP1: {entry - 1.5*risk:.1f}\n"
                f"TP2: {entry - 2.5*risk:.1f}"
            ),
            "confidence": _conf(ctx),
        }
    return {"text": "NO TRADE — regime RANGE / tidak jelas", "confidence": 0}

def setup_orb(ctx):
    # ORB butuh data intraday, versi simplifikasi:
    # kirim level PDH/PDL sebagai acuan breakout sesi NY
    if ctx["regime"] == "TREND UP":
        return {
            "text": (
                f"*Model B — NY Breakout Long*\n"
                f"Kalau break & close M15 di atas PDH {ctx['pdh']:.1f}\n"
                f"Entry: > {ctx['pdh']:.1f}\n"
                f"SL: {ctx['pdc']:.1f}\n"
                f"TP1: {ctx['r1']:.1f}\n"
                f"TP2: {ctx['pdh'] + ctx['atr']:.1f}"
            ),
            "confidence": _conf(ctx),
        }
    if ctx["regime"] == "TREND DOWN":
        return {
            "text": (
                f"*Model B — NY Breakdown Short*\n"
                f"Kalau break & close M15 di bawah PDL {ctx['pdl']:.1f}\n"
                f"Entry: < {ctx['pdl']:.1f}\n"
                f"SL: {ctx['pdc']:.1f}\n"
                f"TP1: {ctx['s1']:.1f}\n"
                f"TP2: {ctx['pdl'] - ctx['atr']:.1f}"
            ),
            "confidence": _conf(ctx),
        }
    return {"text": "NO TRADE — range tidak valid untuk ORB", "confidence": 0}

def _conf(ctx):
    score = 5
    if ctx["adx"] > 25: score += 2
    if abs(ctx["close"] - ctx["ema50"]) / ctx["atr"] < 1.5: score += 1
    if ctx["vix"] < 22: score += 1
    if ctx["vix"] > 30: score -= 3
    return max(1, min(10, score))

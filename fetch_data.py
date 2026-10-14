import yfinance as yf
import pandas as pd
import numpy as np
import yaml

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

def fetch(ticker, period="1y"):
    df = yf.download(ticker, period=period, interval="1d",
                     auto_adjust=False, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

def get_daily_context():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)

    ndx = fetch(cfg["symbol_data"])
    ndx["EMA20"]  = ema(ndx["Close"], cfg["strategy"]["ema_fast"])
    ndx["EMA50"]  = ema(ndx["Close"], cfg["strategy"]["ema_slow"])
    ndx["EMA200"] = ema(ndx["Close"], cfg["strategy"]["ema_trend"])
    ndx["RSI14"]  = rsi(ndx["Close"], cfg["strategy"]["rsi_period"])
    ndx["ATR14"]  = atr(ndx, cfg["strategy"]["atr_period"])
    ndx["ADX14"]  = adx(ndx, cfg["strategy"]["adx_period"])

    vix = fetch(cfg["macro_tickers"]["vix"]).iloc[-1]["Close"]
    dxy = fetch(cfg["macro_tickers"]["dxy"]).iloc[-1]["Close"]
    tnx = fetch(cfg["macro_tickers"]["tnx"]).iloc[-1]["Close"]

    last = ndx.iloc[-1]
    prev = ndx.iloc[-2]

    close = float(last["Close"])
    ema50 = float(last["EMA50"])
    ema200 = float(last["EMA200"])
    adx_v = float(last["ADX14"]) if not np.isnan(last["ADX14"]) else 0

    if close > ema200 and ema50 > ema200 and adx_v > cfg["strategy"]["adx_trend_threshold"]:
        regime = "TREND UP"
        bias = "BULLISH"
    elif close < ema200 and ema50 < ema200 and adx_v > cfg["strategy"]["adx_trend_threshold"]:
        regime = "TREND DOWN"
        bias = "BEARISH"
    else:
        regime = "RANGE"
        bias = "NETRAL"

    pdh = float(prev["High"]); pdl = float(prev["Low"]); pdc = float(prev["Close"])
    pivot = (pdh + pdl + pdc) / 3
    r1 = 2 * pivot - pdl
    s1 = 2 * pivot - pdh

    from datetime import datetime
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    warning = "Tidak ada warning khusus"
    if today_str in cfg.get("high_impact_days", []):
        warning = "⚠️ HARI INI ADA NEWS HIGH IMPACT — lot 50% atau skip"

    return {
        "regime": regime, "bias": bias,
        "close": close,
        "ema20": float(last["EMA20"]),
        "ema50": ema50, "ema200": ema200,
        "rsi": float(last["RSI14"]),
        "atr": float(last["ATR14"]),
        "adx": adx_v,
        "pdh": pdh, "pdl": pdl, "pdc": pdc,
        "pivot": pivot, "r1": r1, "s1": s1,
        "vix": float(vix), "dxy": float(dxy), "tnx": float(tnx),
        "warning": warning,
    }

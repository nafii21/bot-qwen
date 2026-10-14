import yfinance as yf
import pandas as pd
import numpy as np
import yaml

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

def _clean(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()

def fetch(ticker, period="5d", interval="15m"):
    return _clean(yf.download(ticker, period=period, interval=interval,
                              auto_adjust=False, progress=False))

def get_config():
    with open("config.yaml") as f:
        return yaml.safe_load(f)

def get_m15_data():
    """Ambil M15 dan hitung semua indikator."""
    cfg = get_config()
    df = fetch(cfg["symbol_data"], period="10d", interval="15m")
    df["EMA20"] = ema(df["Close"], cfg["strategy"]["ema_fast"])
    df["EMA50"] = ema(df["Close"], cfg["strategy"]["ema_slow"])
    df["ATR14"] = atr(df, cfg["strategy"]["atr_period"])
    df["ADX14"] = adx(df, cfg["strategy"]["adx_period"])
    return df.dropna()

def get_swing_high_low(df, lookback=30):
    """Cari swing high & low dari N candle terakhir."""
    recent = df.tail(lookback)
    return float(recent["High"].max()), float(recent["Low"].min())

def get_fib_levels(swing_high, swing_low, trend):
    """Hitung level Fibonacci retracement."""
    diff = swing_high - swing_low
    if trend == "UP":
        return {
            "0.382": swing_high - 0.382 * diff,
            "0.5":   swing_high - 0.5   * diff,
            "0.618": swing_high - 0.618 * diff,
            "0.786": swing_high - 0.786 * diff,
        }
    else:  # DOWN
        return {
            "0.382": swing_low + 0.382 * diff,
            "0.5":   swing_low + 0.5   * diff,
            "0.618": swing_low + 0.618 * diff,
            "0.786": swing_low + 0.786 * diff,
        }

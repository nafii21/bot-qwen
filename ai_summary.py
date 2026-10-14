import os, requests, json

def summarize(ctx, setup):
    api_key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

    prompt = f"""Kamu asisten trading US100. Rangkum kondisi market dalam 2-3 kalimat bahasa Indonesia santai.
JANGAN mengarang angka. Pakai HANYA data berikut:

Regime: {ctx['regime']}
Bias: {ctx['bias']}
Close: {ctx['close']:.1f}
PDH: {ctx['pdh']:.1f} / PDL: {ctx['pdl']:.1f}
ATR: {ctx['atr']:.1f}
RSI: {ctx['rsi']:.1f}
ADX: {ctx['adx']:.1f}
VIX: {ctx['vix']:.1f}
DXY: {ctx['dxy']:.2f}
US10Y: {ctx['tnx']:.2f}
Setup: {setup['text']}

Cukup jelaskan kenapa setup ini valid atau tidak. Maksimal 3 kalimat."""

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        r = requests.post(url, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        return f"(LLM error: {e})"

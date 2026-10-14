import os
import requests

def summarize(ctx, setup):
    api_key = os.environ["GROQ_API_KEY"]
    # Pastikan URL ini PERSIS sama
    url = "https://api.groq.com/openai/v1/chat/completions"

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

    payload = {
        # Ganti model di sini kalau perlu, tapi ini yang paling stabil
        "model": "openai/gpt-oss-120b",
        "messages": [
            {"role": "system", "content": "Kamu asisten trading yang ringkas dan tidak mengarang data."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        # Cetak error yang lebih detail untuk debugging
        print(f"LLM error: {e}")
        if 'r' in locals():
            print(f"Response body: {r.text}")
        return "(LLM error)"

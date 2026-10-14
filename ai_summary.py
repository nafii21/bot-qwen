import os, requests

def _call_groq(prompt, max_tokens=200):
    api_key = os.environ["GROQ_API_KEY"]
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": "Kamu analis US100. Ringkas, no ngasal angka."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(Groq error: {e})"

def validate_setup(setup, news_info):
    """Minta Groq kasih skor & alasan."""
    prompt = f"""Setup M15 pullback terdeteksi:
Direction: {setup['direction']}
Trend M15: {setup['trend']}
Entry: {setup['entry']} | SL: {setup['sl']} | TP: {setup['tp']}
Risk: {setup['risk_pts']} pts | Reward: {setup['reward_pts']} pts | RR {setup['rr']}
EMA20: {setup['ema20']} | EMA50: {setup['ema50']}
ATR: {setup['atr']} | ADX: {setup['adx']}
Fibonacci confluence: {setup['fib_confluence']} ({setup['fib_note']})
Fib levels: {setup['fibs']}
News high impact dekat: {news_info.get('has_high_impact', False)} — {news_info.get('events', [])}

Tugas: nilai setup ini.
Jawab dalam format PERSIS ini (3 baris):
SCORE: [1-10]
ALASAN: [1-2 kalimat singkat]
WARNING: [1 kalimat warning atau "tidak ada"]"""

    resp = _call_groq(prompt, max_tokens=200)

    # Parse
    score = "?"
    alasan = resp
    warning = ""
    for line in resp.split("\n"):
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            score = line.split(":", 1)[1].strip()
        elif line.upper().startswith("ALASAN:"):
            alasan = line.split(":", 1)[1].strip()
        elif line.upper().startswith("WARNING:"):
            warning = line.split(":", 1)[1].strip()

    return {"score": score, "alasan": alasan, "warning": warning, "raw": resp}

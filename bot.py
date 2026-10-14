import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os
from groq import Groq
from datetime import datetime, timedelta
import pytz

# --- KONFIGURASI (Ganti dengan data lo) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "GANTI_DENGAN_TOKEN_LO")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "GANTI_DENGAN_CHAT_ID_LO")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "GANTI_DENGAN_API_KEY_GROQ_LO")

# Ticker QQQ lebih stabil datanya di yfinance gratis dibanding NQ=F, pergerakan 99% sama dengan US100
TICKER = "QQQ" 
TIMEFRAME = "5m"

def get_data():
    # Ambil data 5 hari terakhir untuk memastikan kita punya data Yesterday High/Low
    df = yf.download(TICKER, period="5d", interval=TIMEFRAME, progress=False)
    if df.empty:
        return None
    
    # Flatten columns jika yfinance mengembalikan multi-index
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    return df

def analyze_setup(df):
    # 1. Tentukan Previous Day High (PDH) dan Low (PDL)
    # Asumsi: baris terakhir adalah hari ini, baris sebelumnya adalah kemarin
    daily_data = df['Close'].resample('1D').agg(['high', 'low', 'close'])
    prev_day_high = daily_data['high'].iloc[-2]
    prev_day_low = daily_data['low'].iloc[-2]
    
    current_price = df['Close'].iloc[-1]
    current_time = df.index[-1].tz_convert('America/New_York')
    
    # 2. Cek Killzone (09:30 - 10:30 EST atau 14:00 - 15:30 EST)
    hour = current_time.hour
    minute = current_time.minute
    is_killzone_1 = (hour == 9 and minute >= 30) or (hour == 10 and minute <= 30)
    is_killzone_2 = (hour >= 14 and hour < 15) or (hour == 15 and minute <= 30)
    
    if not (is_killzone_1 or is_killzone_2):
        return "Bukan jam Killzone. Tidak ada analisa."

    # 3. Logika Sederhana Liquidity Sweep + Reversal (5m)
    # Cek apakah harga saat ini baru saja menyentuh/menembus PDH/PDL tapi close di dalamnya
    # Dan cek apakah ada perubahan momentum (misal: RSI < 30 untuk long sweep, atau > 70 untuk short sweep)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    current_rsi = df['RSI'].iloc[-1]
    
    signal = None
    reason = ""

    # Setup LONG: Sweep PDL + RSI Oversold di Killzone
    if current_price <= prev_day_low * 1.002 and current_price >= prev_day_low * 0.998:
        if current_rsi < 40: # Kondisi oversold lokal
            signal = "POTENTIAL LONG 🟢"
            reason = f"Harga melakukan sweep di area Previous Day Low ({prev_day_low:.2f}) dengan RSI 5m yang oversold ({current_rsi:.1f}) di sesi Killzone."

    # Setup SHORT: Sweep PDH + RSI Overbought di Killzone
    elif current_price >= prev_day_high * 0.998 and current_price <= prev_day_high * 1.002:
        if current_rsi > 60: # Kondisi overbought lokal
            signal = "POTENTIAL SHORT 🔴"
            reason = f"Harga melakukan sweep di area Previous Day High ({prev_day_high:.2f}) dengan RSI 5m yang overbought ({current_rsi:.1f}) di sesi Killzone."

    if signal:
        return {
            "signal": signal,
            "price": current_price,
            "pdh": prev_day_high,
            "pdl": prev_day_low,
            "rsi": current_rsi,
            "reason": reason,
            "time": current_time.strftime("%Y-%m-%d %H:%M:%S EST")
        }
    
    return "Tidak ada setup valid saat ini. Market sedang konsolidasi atau belum menyentuh area likuiditas."

def generate_ai_message(analysis_result):
    if isinstance(analysis_result, str):
        return f"🤖 **NAS100 Daily Monitor**\n\n📊 Status: {analysis_result}\n\n💡 *AI Agent akan terus memantau 2 Killzone harian (NY Open & Afternoon).*"

    # Jika ada setup, minta Groq merapikan bahasanya agar terdengar profesional
    prompt = f"""
    Kamu adalah AI Trading Analyst profesional untuk NASDAQ (US100). 
    Buatlah pesan sinyal trading yang singkat, padat, dan profesional untuk Telegram berdasarkan data ini:
    - Setup: {analysis_result['signal']}
    - Harga Saat Ini: {analysis_result['price']:.2f}
    - Previous Day High: {analysis_result['pdh']:.2f}
    - Previous Day Low: {analysis_result['pdl']:.2f}
    - RSI (5m): {analysis_result['rsi']:.1f}
    - Alasan: {analysis_result['reason']}
    - Waktu: {analysis_result['time']}

    Tambahkan saran Stop Loss (di luar area sweep) dan Risk Management singkat. Gunakan emoji yang relevan tapi jangan berlebihan. Format dengan Markdown Telegram.
    """
    
    client = Groq(api_key=GROQ_API_KEY)
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3-70b-8192", # Model gratis tercepat dan cerdas di Groq
        temperature=0.3, # Rendah agar tidak berhalusinasi
    )
    return chat_completion.choices[0].message.content

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        print("✅ Sinyal berhasil dikirim ke Telegram!")
    else:
        print(f"❌ Gagal kirim: {response.text}")

if __name__ == "__main__":
    print("🔄 Mengambil data market...")
    df = get_data()
    if df is not None:
        print("🧆 Menganalisa setup...")
        result = analyze_setup(df)
        print("🤖 Memformat pesan dengan AI...")
        final_message = generate_ai_message(result)
        print("📤 Mengirim ke Telegram...")
        send_telegram(final_message)
    else:
        send_telegram("⚠️ Gagal mengambil data market. Cek koneksi atau ticker.")

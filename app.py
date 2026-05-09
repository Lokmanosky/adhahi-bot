import os
import time
import requests
import re
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread

# الإعدادات
BOT_TOKEN = "8606991432:AAHKgbdzPIOxMzraegxLioB0mpOtDVQNxSA"
CHANNEL_ID = "@adhaihajz"
ADHAHI_URL = "https://adhahi.dz/register"
CHECK_INTERVAL = 10  # فحص كل 10 ثوانٍ (سريع ومناسب لـ Render)

# تخزين حالة الولايات
wilayas_state = {}

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,ar;q=0.8,en;q=0.7',
}

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def fetch_adhahi_page():
    try:
        response = requests.get(ADHAHI_URL, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"Error fetching page: {e}")
    return None

def parse_wilayas(html_content):
    if not html_content:
        return {}
    
    wilayas = {}
    pattern = r'<option[^>]*>\s*(.*?)\s*[-—|:]\s*(.*?)\s*</option>'
    matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
    
    for wilaya_name, status in matches:
        wilaya_name = wilaya_name.strip()
        status_text = status.strip()
        
        if "اختر" in wilaya_name or "choisir" in wilaya_name.lower():
            continue
            
        is_open = "غير متوفر" not in status_text and "fermé" not in status_text.lower() and "no" not in status_text.lower()
        
        wilayas[wilaya_name] = {
            "status": "OPEN" if is_open else "CLOSED",
            "raw_status": status_text
        }
    return wilayas

def check_and_notify():
    global wilayas_state
    html = fetch_adhahi_page()
    if not html:
        return
    
    current_wilayas = parse_wilayas(html)
    if not current_wilayas:
        return
    
    for wilaya, data in current_wilayas.items():
        current_status = data["status"]
        previous_status = wilayas_state.get(wilaya, {}).get("status")
        
        if previous_status != current_status and previous_status is not None:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            if current_status == "OPEN":
                message = f"🟢 **ALERTE : Réservations Ouvertes !**\n\n📍 Wilaya disponible : **{wilaya}** ✅\n\n⏰ {now}\n\n🔗 [Lien de réservation direct]({ADHAHI_URL})"
                send_telegram_message(message)
            elif current_status == "CLOSED" and previous_status == "OPEN":
                message = f"🔴 **Fermé : {wilaya}**\n\n⏰ {now}"
                send_telegram_message(message)
                
        wilayas_state[wilaya] = data

def monitoring_loop():
    while True:
        try:
            check_and_notify()
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(CHECK_INTERVAL)

@app.route('/')
def index():
    return f"Bot is running. Monitored wilayas: {len(wilayas_state)}"

# تشغيل الفحص الخلفي في Thread منفصل
monitoring_thread = Thread(target=monitoring_loop, daemon=True)
monitoring_thread.start()

# رسالة ترحيبية عند أول تشغيل للبوت لنتأكد أنه متصل
send_telegram_message("🚀 **Bot Adhahi.dz démarré avec succès !**\n\n✅ Surveillance active des réservations...")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=False)

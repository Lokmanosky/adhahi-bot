import os
import time
import requests
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread

# الإعدادات الأساسية لقناتك والبوت
BOT_TOKEN = "8606991432:AAHKgbdzPIOxMzraegxLioB0mpOtDVQNxSA"
CHANNEL_ID = "@adhaihajz"

# الرابط السري المكتشف من الـ F12
ADHAHI_API_URL = "https://adhahi.dz/api/v1/public/wilaya-quotas"
ADHAHI_REGISTER_URL = "https://adhahi.dz/register"
CHECK_INTERVAL = 10  # الفحص كل 10 ثوانٍ

# تخزين الحالات السابقة لمنع تكرار الإرسال
wilayas_state = {}

app = Flask(__name__)

# الهيدرز المطابقة تماماً لطلب المتصفح الحقيقي من صورك
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'ar-DZ,ar;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://adhahi.dz/register'
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
        print(f"Error sending to Telegram: {e}")

def check_and_notify():
    global wilayas_state
    try:
        # جلب البيانات مباشرة بصيغة JSON من الـ API الحقيقي
        response = requests.get(ADHAHI_API_URL, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Failed to fetch API. Status code: {response.status_code}")
            return
            
        data = response.json()
        
        # عند أول فحص ناجح والتحقق من وجود بيانات
        if data and not wilayas_state:
            send_telegram_message("🚀 **Bot Adhahi.dz يعمل بنجاح الآن!**\n\n✅ تم ربط السيرفر بالـ API المباشر للموقع وجاري مراقبة الولايات بانتظام.")

        current_wilayas = {}
        for item in data:
            name = item.get('wilaya_name')
            if not name:
                continue
            
            # قراءة الإتاحة الفعلية من بيانات الـ API
            # إذا كان الحقل available مساوياً لـ True أو الحصة المتبقية أكبر من 0
            is_available = item.get('available', False) or item.get('quota_remaining', 0) > 0
            
            current_wilayas[name] = "OPEN" if is_available else "CLOSED"

        # مقارنة الحالات الحالية بالسابقة لإرسال التنبيهات
        for wilaya, status in current_wilayas.items():
            previous_status = wilayas_state.get(wilaya)
            
            if previous_status != status and previous_status is not None:
                now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                if status == "OPEN":
                    message = f"🟢 **ALERTE : Réservations Ouvertes !**\n\n📍 Wilaya disponible : **{wilaya}** ✅\n\n⏰ {now}\n\n🔗 [Lien de réservation direct]({ADHAHI_REGISTER_URL})"
                    send_telegram_message(message)
                elif status == "CLOSED" and previous_status == "OPEN":
                    message = f"🔴 **Fermé : {wilaya}**\n\n⏰ {now}"
                    send_telegram_message(message)
            
            # تحديث الحالة المخزنة
            wilayas_state[wilaya] = status

    except Exception as e:
        print(f"Error checking API: {e}")

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

# تشغيل حلقة الفحص في الخلفية
monitoring_thread = Thread(target=monitoring_loop, daemon=True)
monitoring_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000, debug=False)

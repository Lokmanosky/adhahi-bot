import os
import time
import requests
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread

# ====================
# الإعدادات
# ====================

BOT_TOKEN = "8606991432:AAHKgbdzPIOxMzraegxLioB0mpOtDVQNxSA"
CHANNEL_ID = "@adhaihajz"

ADHAHI_URL = "https://adhahi.dz/register"
ADHAHI_API_URL = "https://adhahi.dz/api/v1/public/wilaya-quotas"

CHECK_INTERVAL = 10  # فحص كل 10 ثوانٍ

# تخزين حالة الولايات في الذاكرة
wilayas_state = {}

app = Flask(__name__)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ar-DZ,ar;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": ADHAHI_URL,
}


# ====================
# دوال مساعدة للـ Logs
# ====================

def log(msg: str):
    """طباعة log واضح (Render يلتقط stdout في صفحة Logs)."""
    print(f"[ADHAHI] {msg}", flush=True)


# ====================
# Telegram
# ====================

def send_telegram_message(text: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        log(f"Telegram response: {r.status_code} - {r.text[:200]}")
    except Exception as e:
        log(f"Error sending Telegram message: {e}")


# ====================
# جلب JSON من API
# ====================

def fetch_wilaya_quotas():
    """جلب JSON الخاص بحصص الولايات من API المباشر."""
    try:
        log(f"Fetching {ADHAHI_API_URL} ...")
        r = requests.get(ADHAHI_API_URL, headers=HEADERS, timeout=15)
        log(f"GET {ADHAHI_API_URL} -> {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            # طباعة مفاتيح / حجم البيانات لفهم البنية
            if isinstance(data, dict):
                log(f"Root JSON keys: {list(data.keys())}")
            elif isinstance(data, list):
                log(f"Root JSON is list with {len(data)} items")
            return data
        else:
            log(f"Non-200 status code from API: {r.status_code}")
    except Exception as e:
        log(f"Error fetching API: {e}")
    return None


# ====================
# تحليل JSON واستخراج الولايات
# ====================

def parse_wilayas_from_json(data):
    """
    تحويل JSON القادم من API إلى:
    { 'اسم الولاية': { 'status': OPEN/CLOSED, 'raw_status': نص توضيحي } }
    """
    wilayas = {}
    if not data:
        log("No data passed to parse_wilayas_from_json.")
        return wilayas

    try:
        # تحديد القائمة التي تحتوي على العناصر
        if isinstance(data, dict):
            # إذا فيه مفتاح اسمه data وهو list
            if "data" in data and isinstance(data["data"], list):
                items = data["data"]
            else:
                # ابحث عن أول قيمة نوعها list
                list_values = [v for v in data.values() if isinstance(v, list)]
                if list_values:
                    items = list_values[0]
                else:
                    log("Could not find list of items inside dict JSON.")
                    return wilayas
        elif isinstance(data, list):
            items = data
        else:
            log(f"Unexpected JSON root type: {type(data)}")
            return wilayas

        log(f"Parsing {len(items)} items from JSON...")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue

            # طباعة أول 5 عناصر لفهم شكل الـ JSON الحقيقي
            if idx < 5:
                log(f"Quota item #{idx+1}: {item}")

            # ----- استخراج اسم الولاية -----
            name = ""
            for key, value in item.items():
                key_l = str(key).lower()
                if "wilaya" in key_l or "ولاية" in key_l or "nom" in key_l or "name" in key_l:
                    name = str(value).strip()
                    if name:
                        break

            if not name:
                # fallback: إن لم نجد أي شيء نعتبره ليس عن ولاية
                continue

            # ----- تحديد الحقل العددي الذي يمثل الكمية/المتبقي -----
            remaining = None
            # أولوية لمفاتيح تحتوي على quota / remaining / dispo
            for key, value in item.items():
                key_l = str(key).lower()
                if any(x in key_l for x in ["remaining", "disponible", "available", "quota", "reste", "restant"]):
                    try:
                        remaining = int(value)
                    except Exception:
                        try:
                            remaining = int(float(value))
                        except Exception:
                            pass
                    if remaining is not None:
                        break

            # لو ما حصلنا، نبحث عن أي رقم آخر كخطة احتياطية
            if remaining is None:
                for key, value in item.items():
                    if isinstance(value, (int, float)):
                        remaining = int(value)
                        break

            # ----- استخراج status_text لو موجود -----
            status_text = ""
            for key, value in item.items():
                key_l = str(key).lower()
                if "status" in key_l or "etat" in key_l:
                    status_text = str(value).strip()
                    break

            # ----- تحديد مفتوح / مغلق -----
            is_open = False
            if remaining is not None:
                is_open = remaining > 0

            # لو ما فيه رقم، حاول استنتاجه من status_text نفسه
            joined = (status_text + " " + " ".join(str(v) for v in item.values())).lower()
            closed_keywords = [
                "غير متوفر",
                "غير متاحة",
                "غير متاح",
                "مغلقة",
                "مغلق",
                "fermé",
                "fermée",
                "ferme",
                "closed",
                "no disponible",
                "non disponible",
                "pas disponible",
                "épuisé",
            ]
            if any(kw in joined for kw in closed_keywords):
                is_open = False

            status = "OPEN" if is_open else "CLOSED"
            raw = status_text if status_text else f"remaining={remaining}"

            wilayas[name] = {
                "status": status,
                "raw_status": raw,
            }

            log(f"Parsed wilaya: '{name}' -> {status} (raw='{raw}')")

        log(f"Total parsed wilayas from JSON: {len(wilayas)}")

    except Exception as e:
        log(f"Error in parse_wilayas_from_json: {e}")

    return wilayas


# ====================
# فحص وتحديث + إشعارات
# ====================

def check_and_notify():
    global wilayas_state

    data = fetch_wilaya_quotas()
    if not data:
        log("No data returned from fetch_wilaya_quotas.")
        return

    current_wilayas = parse_wilayas_from_json(data)
    if not current_wilayas:
        log("parse_wilayas_from_json returned 0 wilayas.")
        return

    # رسالة تشغيل أول مرة
    if current_wilayas and not wilayas_state:
        send_telegram_message(
            "🚀 **Bot Adhahi.dz يعمل بنجاح الآن!**\n\n"
            "✅ تم ربط السيرفر بنجاح وجاري مراقبة الولايات بانتظام."
        )

    # مقارنة الحالات القديمة بالجديدة
    for wilaya, data in current_wilayas.items():
        current_status = data["status"]
        previous_status = wilayas_state.get(wilaya, {}).get("status")

        if previous_status != current_status and previous_status is not None:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

            if current_status == "OPEN":
                # تنبيه فتح الحجز
                message = (
                    "🟢 **ALERTE : Réservations Ouvertes !**\n\n"
                    f"📍 Wilaya disponible : **{wilaya}** ✅\n\n"
                    f"⏰ {now}\n\n"
                    f"🔗 [Lien de réservation direct]({ADHAHI_URL})"
                )
                send_telegram_message(message)

            elif current_status == "CLOSED" and previous_status == "OPEN":
                # تنبيه غلق الحجز
                message = (
                    f"🔴 **Fermé : {wilaya}**\n\n"
                    f"⏰ {now}"
                )
                send_telegram_message(message)

        # تحديث الحالة المخزّنة
        wilayas_state[wilaya] = data

    log(f"Check complete. Currently tracking {len(wilayas_state)} wilayas.")


# ====================
# حلقة المراقبة في Thread
# ====================

def monitoring_loop():
    log("Monitoring loop started.")
    while True:
        try:
            check_and_notify()
        except Exception as e:
            # لا نسمح لأي استثناء بإيقاف الـ Thread
            log(f"Loop error: {e}")
        time.sleep(CHECK_INTERVAL)


# ====================
# Flask routes
# ====================

@app.route("/")
def index():
    return f"Bot is running. Monitored wilayas: {len(wilayas_state)}"


@app.route("/debug")
def debug():
    """للعرض اليدوي من المتصفح إن أردت رؤية الحالة."""
    return jsonify(
        {
            "monitored_wilayas_count": len(wilayas_state),
            "wilayas": wilayas_state,
        }
    )


# تشغيل الفحص الخلفي في Thread منفصل
monitoring_thread = Thread(target=monitoring_loop, daemon=True)
monitoring_thread.start()


if __name__ == "__main__":
    # Render يعطيك PORT في متغير البيئة غالباً
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=False)

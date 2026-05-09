import os
import sys
import time
import requests
import re
from datetime import datetime
from flask import Flask, jsonify
from threading import Thread

# ====================
# الإعدادات
# ====================

BOT_TOKEN = "8606991432:AAHKgbdzPIOxMzraegxLioB0mpOtDVQNxSA"
CHANNEL_ID = "@adhaihajz"
ADHAHI_URL = "https://adhahi.dz/register"
CHECK_INTERVAL = 10  # فحص كل 10 ثوانٍ

# تخزين حالة الولايات في الذاكرة
wilayas_state = {}

# Flag حتى لا نطبع عينة HTML كاملة في كل دورة
html_sample_logged = False

app = Flask(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,ar;q=0.8,en;q=0.7",
}

# ====================
# دوال مساعدة للـ Logs
# ====================

def log(msg):
    """طباعة log واضح في Render (stdout تلتقطه Render تلقائياً)."""
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
# جلب صفحة adhahi.dz
# ====================

def fetch_adhahi_page():
    global html_sample_logged
    try:
        log(f"Fetching {ADHAHI_URL} ...")
        response = requests.get(ADHAHI_URL, headers=HEADERS, timeout=15)
        log(f"GET {ADHAHI_URL} -> {response.status_code}")

        if response.status_code == 200:
            html = response.text

            # طباعة عينة من HTML مرة واحدة فقط (لمساعدتك في فهم البنية)
            if not html_sample_logged:
                sample = html[:2000]
                log("HTML sample (first 2000 chars):")
                log(sample.replace("\n", "\\n"))
                html_sample_logged = True

            return html
        else:
            log(f"Non-200 status code: {response.status_code}")
    except Exception as e:
        log(f"Error fetching page: {e}")
    return None


# ====================
# تحليل الولايات
# ====================

def parse_wilayas(html_content: str):
    """استخراج الولايات وحالة الحجز من HTML بأكبر قدر ممكن من المرونة."""
    if not html_content:
        return {}

    wilayas = {}
    try:
        # استخراج كل ما بين <option>...</option>
        option_blocks = re.findall(
            r"<option[^>]*>(.*?)</option>",
            html_content,
            re.IGNORECASE | re.DOTALL,
        )

        log(f"Found {len(option_blocks)} <option> blocks in HTML.")

        # طباعة عينة من الخيارات لاكتشاف البنية الحقيقية
        for idx, raw_opt in enumerate(option_blocks[:15]):
            clean_opt = re.sub(r"\s+", " ", raw_opt).strip()
            log(f"Option sample #{idx+1}: '{clean_opt}'")

        if not option_blocks:
            log("No <option> tags found at all. ربما يتم تحميلها عبر JavaScript.")
            return {}

        for raw_opt in option_blocks:
            try:
                # تنظيف الفراغات
                text = re.sub(r"\s+", " ", raw_opt).strip()
                if not text:
                    continue

                lower = text.lower()

                # تخطي الخيارات الافتراضية مثل "اختر الولاية" أو "Choisir..."
                if (
                    "اختر" in text
                    or "إختر" in text
                    or "choisir" in lower
                    or "selectionnez" in lower
                    or "select" in lower
                ):
                    continue

                # محاولة فصل اسم الولاية عن حالة الحجز
                wilaya_name = None
                status_text = ""

                # 1) فواصل شائعة: - — | :
                parts = re.split(r"\s*[-—|:]\s*", text, maxsplit=1)
                if len(parts) == 2:
                    wilaya_name = parts[0].strip()
                    status_text = parts[1].strip()
                else:
                    # 2) شكل: "اسم الولاية (حالة الحجز)"
                    m = re.match(r"^(.*?)\s*[\(\[]\s*(.+?)\s*[\)\]]\s*$", text)
                    if m:
                        wilaya_name = m.group(1).strip()
                        status_text = m.group(2).strip()
                    else:
                        # 3) لا يوجد فاصل واضح: نعتبر النص كله اسم ولاية
                        wilaya_name = text
                        status_text = ""

                if not wilaya_name:
                    continue

                # تحديد حالة الحجز من خلال كلمات مفتاحية في النص الكامل
                full_for_status = (wilaya_name + " " + status_text + " " + text).lower()

                closed_keywords = [
                    "غير متوفر",
                    "غير متاحة",
                    "غير متاح",
                    "مغلقة",
                    "مغلق",
                    "مغلق حاليا",
                    "non disponible",
                    "pas disponible",
                    "fermé",
                    "fermée",
                    "ferme",
                    "closed",
                    "unavailable",
                ]

                is_closed = any(kw in full_for_status for kw in closed_keywords)

                status = "CLOSED" if is_closed else "OPEN"

                wilayas[wilaya_name] = {
                    "status": status,
                    "raw_status": status_text if status_text else text,
                }

                log(f"Parsed wilaya: '{wilaya_name}' -> {status} (raw='{status_text}')")

            except Exception as e_opt:
                log(f"Error parsing option '{raw_opt}': {e_opt}")

    except Exception as e:
        log(f"Error in parse_wilayas: {e}")

    log(f"Total parsed wilayas: {len(wilayas)}")
    return wilayas


# ====================
# فحص وتحديث + إشعارات
# ====================

def check_and_notify():
    global wilayas_state

    html = fetch_adhahi_page()
    if not html:
        log("No HTML returned from fetch_adhahi_page.")
        return

    current_wilayas = parse_wilayas(html)
    if not current_wilayas:
        log("parse_wilayas returned 0 wilayas.")
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time, requests
from datetime import datetime
from threading import Thread

BOT_TOKEN = "8606991432:AAHKgbdzPIOxMzraegxLioB0mpOtDVQNxSA"
CHANNEL_ID = -1003905001333
GROUP_ID   = -1003773850093
ADHAHI_URL = "https://adhahi.dz/register"
ADHAHI_API_URL = "https://adhahi.dz/api/v1/public/wilaya-quotas"
CHECK_INTERVAL = 10
UPDATES_INTERVAL = 2

wilayas_state = {}
last_update_id = None
subscribers = {}
sessions = {}

# قائمة الولايات الرسمية 58 ولاية (بدون كلمة "ولاية")
WILAYAS = [
    "أدرار", "الشلف", "الأغواط", "أم البواقي", "باتنة", "بجاية", "بسكرة", "بشار",
    "البليدة", "البويرة", "تمنراست", "تبسة", "تلمسان", "تيارت", "تيزي وزو", "الجزائر",
    "الجلفة", "جيجل", "سطيف", "سعيدة", "سكيكدة", "سيدي بلعباس", "عنابة", "قالمة",
    "قسنطينة", "المدية", "مستغانم", "المسيلة", "معسكر", "ورقلة", "وهران", "البيض",
    "إليزي", "برج بوعريريج", "بومرداس", "الطارف", "تندوف", "تيسمسيلت", "الوادي",
    "خنشلة", "سوق أهراس", "تيبازة", "ميلة", "عين الدفلى", "النعامة", "عين تموشنت",
    "غرداية", "غليزان", "تيميمون", "برج باجي مختار", "أولاد جلال", "بني عباس",
    "إن صالح", "إن قزام", "تقرت", "جانت", "المغير", "المنيعة"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": ADHAHI_URL,
}

def log(msg):
    print("[BOT] " + str(msg), flush=True)

def api_post(method, payload):
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/" + method
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r
    except Exception as e:
        log("api_post error: " + str(e))
        return None

def send_text(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    api_post("sendMessage", payload)

# ======================= اختيار الولاية =======================

def send_wilaya_keyboard(chat_id, names=None, title="📍 *اختر ولايتك:*"):
    if names is None:
        names = WILAYAS
    keyboard = []
    row = []
    for w in names:
        row.append({"text": w, "callback_data": "w:" + w})
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    # أزرار البحث والكتابة اليدوية فقط في الحالة العامة
    if names is WILAYAS:
        keyboard.append([
            {"text": "🔎 بحث عن ولاية", "callback_data": "search"},
            {"text": "⌨️ كتابة الولاية", "callback_data": "manual"}
        ])
    keyboard.append([{"text": "❌ إلغاء", "callback_data": "cancel"}])
    send_text(chat_id, title, reply_markup={"inline_keyboard": keyboard})

def set_subscription_wilaya(chat_id, wilaya):
    subscribers[chat_id] = {"mode": "custom", "wilaya": wilaya}
    sessions.pop(chat_id, None)
    send_text(chat_id, "📍 تم الاشتراك في تنبيهات ولاية *" + wilaya + "* ✅")
    send_main_menu(chat_id)

def find_wilayas(query):
    q = query.replace("ولاية", "").strip()
    if not q:
        return []
    return [w for w in WILAYAS if q in w]

# ======================= القائمة الرئيسية =======================

def send_main_menu(chat_id):
    sub = subscribers.get(chat_id)
    if sub:
        if sub.get("mode") == "all":
            status = "✅ مشترك - كل الولايات"
        elif sub.get("mode") == "custom":
            status = "✅ مشترك - " + str(sub.get("wilaya",""))
        else:
            status = "⚠️ غير مشترك"
    else:
        status = "⚠️ غير مشترك"

    kb = {
        "keyboard": [
            [{"text": "🌍 كل الولايات"}, {"text": "📍 ولايتي فقط"}],
            [{"text": "⏸️ إيقاف التنبيهات"}, {"text": "📊 حالة الولايات"}],
            [{"text": "🔁 تغيير الولاية"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

    msg = (
        "🐏 *بوت تنبيهات الأضاحي | Adhahi Alerts*"
        "📢 " + status + ""
        "🔧 لتغيير الولاية أو إعدادات التنبيهات، اختر من الأزرار بالأسفل:"
    )
    send_text(chat_id, msg, reply_markup=kb)

# ======================= رسائل التنبيهات =======================

def msg_open(wilaya, now):
    return (
  "🟢🔔 تنبيه أضحي | Adhahi Alertn\n"
   "✅ الحجوزات مفتوحة! \n"
        f"📍 الولاية : {wilaya}\n"
        f"\n🕐  الوقت : {now}n\n"
        "🏃 سارع وسجل \n"
        f"🔗 {ADHAHI_URL}"
    )

def msg_closed(wilaya, now):
    return (
        "🔴❌ تنبيه أضحي | Adhahi Alert \n"
        "🚫 الحجوزات مغلقة!\n"
        f"📍 الولاية : {wilaya}\n"
        f"\n🕐 الوقت: {now}\n"
   
    )

def msg_summary():
    if not wilayas_state:
        return "⏳ لا توجد بيانات بعد."
    op  = [w for w, d in wilayas_state.items() if d.get("status") == "OPEN"]
    cl  = [w for w, d in wilayas_state.items() if d.get("status") == "CLOSED"]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return (
        "📊 ملخص الحجوزات | Adhahi Summary"
        f" مفتوحة |: {len(op)} \n "
        f" مغلقة |: {len(cl)} \n "
        f" إجمالي الولايات |: {len(wilayas_state)} \n "
        f" الوقت |: {now}\n "
        "🔗 رابط التسجيل | Register link:"
        f"{ADHAHI_URL}"
    )

# ======================= الإرسال الجماعي =======================
def broadcast_alert(text, wilaya):
    for target in [CHANNEL_ID, GROUP_ID]:
        send_text(target, text)
    for cid, sub in list(subscribers.items()):
        if sub.get("mode") == "all":
            send_text(cid, text)
        elif sub.get("mode") == "custom" and sub.get("wilaya") == wilaya:
            send_text(cid, text)
# ======================= جلب بيانات API =======================

def fetch_wilaya_quotas():
    try:
        r = requests.get(ADHAHI_API_URL, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log("Fetch error: " + str(e))
    return None

def parse_wilayas_from_json(data):
    wilayas = {}
    if not data:
        return wilayas
    try:
        if isinstance(data, dict):
            if "data" in data and isinstance(data["data"], list):
                items = data["data"]
            else:
                lv = [v for v in data.values() if isinstance(v, list)]
                items = lv[0] if lv else []
        elif isinstance(data, list):
            items = data
        else:
            return wilayas
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            if idx < 3:
                log("Item #" + str(idx+1) + ": " + str(item))
            name = str(item.get("wilayaNameAr") or item.get("wilaya_name_ar") or "").strip()
            if not name:
                continue
            av = item.get("available")
            if isinstance(av, bool):
                is_open = av
            else:
                rem = next((int(v) for v in item.values() if isinstance(v,(int,float))), None)
                is_open = bool(rem and rem > 0)
            wilayas[name] = {"status": "OPEN" if is_open else "CLOSED"}
        log("Parsed: " + str(len(wilayas)))
    except Exception as e:
        log("Parse error: " + str(e))
    return wilayas

def check_and_notify():
    global wilayas_state
    data = fetch_wilaya_quotas()
    if not data:
        return
    current = parse_wilayas_from_json(data)
    if not current:
        return
    for wilaya, d in current.items():
        cur  = d["status"]
        prev = wilayas_state.get(wilaya, {}).get("status")
        if prev is not None and prev != cur:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if cur == "OPEN":
                broadcast_alert(msg_open(wilaya, now), wilaya)
            elif cur == "CLOSED":
                broadcast_alert(msg_closed(wilaya, now), wilaya)
        wilayas_state[wilaya] = d
    log("Done. " + str(len(wilayas_state)) + " wilayas.")

def monitoring_loop():
    while True:
        try:
            check_and_notify()
        except Exception as e:
            log("Monitor error: " + str(e))
        time.sleep(CHECK_INTERVAL)

# ======================= التعامل مع الكول باك =======================

def handle_callback(cb):
    data    = cb.get("data","")
    chat_id = cb.get("from",{}).get("id")
    msg_id  = cb.get("message",{}).get("message_id")
    api_post("answerCallbackQuery", {"callback_query_id": cb.get("id","")})
    if msg_id:
        api_post("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})

    if data.startswith("w:"):
        wilaya = data[2:]
        if wilaya in WILAYAS:
            set_subscription_wilaya(chat_id, wilaya)
        else:
            send_text(chat_id, "⚠️ حدث خطأ في اسم الولاية، حاول من جديد.")
    elif data == "search":
        sessions[chat_id] = {"mode": "search_wilaya"}
        send_text(chat_id, "🔎 أرسل جزءًا من اسم الولاية (مثال: قزام، وهر، غليزان...).")
    elif data == "manual":
        sessions[chat_id] = {"mode": "manual_wilaya"}
        send_text(chat_id, "⌨️ أرسل اسم ولايتك بالضبط (مثال: إن قزام).")
    elif data == "cancel":
        sessions.pop(chat_id, None)
        send_main_menu(chat_id)

# ======================= التعامل مع الرسائل =======================

def handle_message(message):
    text    = str(message.get("text","")).strip()
    chat_id = message.get("chat",{}).get("id")
    if not chat_id or not text:
        return

    # لو فيه جلسة بحث/إدخال يدوي، نعالجها أولاً
    session = sessions.get(chat_id)
    if session:
        mode = session.get("mode")
        if mode == "search_wilaya":
            matches = find_wilayas(text)
            if not matches:
                send_text(chat_id, "⚠️ لم أجد ولايات توافق هذا الاسم.حاول جزء آخر من الاسم.")
                return
            if len(matches) == 1:
                set_subscription_wilaya(chat_id, matches[0])
                return
            # أكثر من نتيجة -> كيبورد بالنتائج
            rows = []
            row = []
            for w in matches:
                row.append({"text": w, "callback_data": "w:" + w})
                if len(row) == 2:
                    rows.append(row)
                    row = []
            if row:
                rows.append(row)
            rows.append([{"text": "❌ إلغاء", "callback_data": "cancel"}])
            send_text(chat_id, "اختر ولايتك من النتائج التالية:", reply_markup={"inline_keyboard": rows})
            return

        elif mode == "manual_wilaya":
            name = text.replace("ولاية", "").strip()
            if name in WILAYAS:
                set_subscription_wilaya(chat_id, name)
                return
            similar = find_wilayas(name)
            msg = "⚠️ لم أجد ولاية بهذا الاسم.تأكد من الكتابة الصحيحة."
            if similar:
              msg += (  "قد تقصد واحدة من التالي:- " + "- ".join(similar) )
              send_text(chat_id, msg)
              return

    # أوامر عادية
    if text.startswith("/start") or text == "/start":
        send_main_menu(chat_id)
    elif "كل الولايات" in text:
        subscribers[chat_id] = {"mode": "all", "wilaya": None}
        send_text(chat_id, "🌍 تم الاشتراك بكل الولايات ✅")
        send_main_menu(chat_id)
    elif "ولايتي" in text or "تغيير الولاية" in text:
        send_wilaya_keyboard(chat_id)
    elif "إيقاف التنبيهات" in text:
        if chat_id in subscribers:
            del subscribers[chat_id]
        sessions.pop(chat_id, None)
        send_text(chat_id, "⏸️ تم إيقاف التنبيهات ❌")
        send_main_menu(chat_id)
    elif "حالة الولايات" in text:
        send_text(chat_id, msg_summary())

# ======================= حلقة التحديثات =======================

def updates_loop():
    global last_update_id
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getUpdates"
    while True:
        try:
            params = {"timeout": 20, "allowed_updates": ["message","callback_query"]}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1
            r = requests.get(url, params=params, timeout=30)
            if r.status_code == 200:
                for update in r.json().get("result",[]):
                    last_update_id = update.get("update_id", last_update_id)
                    if "callback_query" in update:
                        handle_callback(update["callback_query"])
                    elif "message" in update or "edited_message" in update:
                        handle_message(update.get("message") or update.get("edited_message"))
            time.sleep(UPDATES_INTERVAL)
        except Exception as e:
            log("Updates error: " + str(e))
            time.sleep(UPDATES_INTERVAL)

def main():
    Thread(target=monitoring_loop, daemon=True).start()
    updates_loop()

if __name__ == "__main__":
    main()


import os
import re
import sqlite3
import random
import datetime
from threading import Thread
from flask import Flask
import telebot
from telebot import types

# ==================== البيانات الأساسية ====================
BOT_TOKEN = "8776743286:AAHeD1IQgC5u9kIjA7Ov0qvAl2RY42bmYBc"
SUPER_ADMIN_ID = 8577656131
DEV_CHANNEL_URL = "https://t.me/lerafree"
DEV_CHANNEL_USERNAME = "lerafree"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== سيرفر Flask المدمج ====================
app = Flask(__name__)

@app.route('/')
def home():
    return "AUREX Bot Web Server is Active!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==================== قاعدة البيانات ====================
def get_db():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            phone TEXT,
            balance REAL DEFAULT 0,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            withdrawals_count INTEGER DEFAULT 0,
            captcha_passed INTEGER DEFAULT 0,
            last_withdraw DATETIME,
            last_daily DATETIME,
            last_weekly DATETIME,
            last_promo DATETIME,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    
    # جدول المشرفين
    cursor.execute('CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)')
    cursor.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (SUPER_ADMIN_ID,))
    
    # جدول الإعدادات
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    # إعدادات افتراضية
    default_settings = {
        "min_withdraw_syriatel": "50",
        "max_withdraw_syriatel": "50",
        "min_withdraw_sham": "50",
        "max_withdraw_sham": "50",
        "withdraw_cooldown_hours": "72",
        "promo_cooldown_hours": "6",
        "ref_reward": "5",
        "daily_reward": "1",
        "weekly_reward": "5",
        "welcome_bonus_active": "0",
        "welcome_bonus_amount": "0",
        "maintenance_mode": "0"
    }
    for k, v in default_settings.items():
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (k, v))
        
    # جدول الأكواد
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            reward REAL,
            max_uses INTEGER,
            current_uses INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # جدول القنوات الإجبارية
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            url TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==================== أدوات مساعدة ====================
def get_setting(key):
    conn = get_db()
    res = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return res['value'] if res else None

def set_setting(key, value):
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = get_db()
    res = conn.execute("SELECT user_id FROM admins WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return res is not None

def get_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return user

def update_balance(user_id, amount):
    conn = get_db()
    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()

# ==================== التفاعل التلقائي على الرسائل ====================
REACTIONS = ['👍', '❤️', '🔥', '👏', '🎉', '⚡️', '🤩', '👌']

def send_random_reaction(chat_id, message_id):
    try:
        emoji = random.choice(REACTIONS)
        bot.set_message_reaction(chat_id, message_id, [types.ReactionTypeEmoji(emoji)])
    except Exception:
        pass

# ==================== التحقق من القنوات والأمان ====================
def check_sub(user_id):
    # قناة المبرمج الأساسية
    try:
        member = bot.get_chat_member(f"@{DEV_CHANNEL_USERNAME}", user_id)
        if member.status in ['left', 'kicked']:
            return False
    except Exception:
        pass

    # القنوات الإضافية
    conn = get_db()
    channels = conn.execute("SELECT channel_id FROM channels").fetchall()
    conn.close()
    
    for ch in channels:
        try:
            member = bot.get_chat_member(ch['channel_id'], user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            continue
    return True

# ==================== القوائم والأزرار الشات ====================
def main_menu_keyboard(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("💰 رصيدي", callback_data="user_balance"),
        types.InlineKeyboardButton("💳 سحب رصيد", callback_data="user_withdraw"),
        types.InlineKeyboardButton("🎁 هدية يومية", callback_data="user_daily"),
        types.InlineKeyboardButton("🏆 هدية اسبوعية", callback_data="user_weekly"),
        types.InlineKeyboardButton("🎟 ادخال كود هدية", callback_data="user_promo"),
        types.InlineKeyboardButton("🔗 رابط احالتي", callback_data="user_referral"),
        types.InlineKeyboardButton("📢 قناة المبرمج", url=DEV_CHANNEL_URL),
        types.InlineKeyboardButton("💬 التواصل مع الدعم", callback_data="user_support")
    )
    if is_admin(user_id):
        kb.add(types.InlineKeyboardButton("⚙️ لوحة الإدارة", callback_data="admin_panel"))
    return kb

def admin_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔍 تفاصيل عميل", callback_data="adm_user_info"),
        types.InlineKeyboardButton("➕ إضافة أدمن", callback_data="adm_add_admin"),
        types.InlineKeyboardButton("📢 إضافة قناة اشتراك", callback_data="adm_add_channel"),
        types.InlineKeyboardButton("🎟 توليد كود هدية", callback_data="adm_gen_code"),
        types.InlineKeyboardButton("❌ إلغاء كود", callback_data="adm_del_code"),
        types.InlineKeyboardButton("🔄 تصفير الأرصدة", callback_data="adm_reset_balances"),
        types.InlineKeyboardButton("🛠 وضع الصيانة", callback_data="adm_toggle_maint"),
        types.InlineKeyboardButton("✉️ رسالة خاصة", callback_data="adm_private_msg"),
        types.InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("⚙️ إعدادات الأسعار والحدود", callback_data="adm_settings_config"),
        types.InlineKeyboardButton("🚫 حظر/إلغاء حظر", callback_data="adm_ban_user"),
        types.InlineKeyboardButton("📊 إحصائيات", callback_data="adm_stats"),
        types.InlineKeyboardButton("🏆 سجل اللاعبين", callback_data="adm_leaderboard")
    )
    return kb

# ==================== المعالجة الرئيسية /start ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    send_random_reaction(message.chat.id, message.message_id)
    user_id = message.from_user.id
    
    # فحص الصيانة
    if get_setting("maintenance_mode") == "1" and not is_admin(user_id):
        bot.send_message(user_id, "⚠️ البوت حالياً في وضع الصيانة، يرجى المحاولة لاحقاً.")
        return

    conn = get_db()
    user = get_user(user_id)
    
    # استخراج كود الإحالة إن وجد
    args = message.text.split()
    ref_by = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None

    if not user:
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)",
            (user_id, message.from_user.username, message.from_user.first_name, ref_by)
        )
        conn.commit()
    conn.close()

    user = get_user(user_id)
    if user['is_banned']:
        bot.send_message(user_id, "❌ أنت محظور من استخدام البوت.")
        return

    # 1. اختبار رقم الهاتف السوري
    if not user['phone']:
        kb = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        kb.add(types.KeyboardButton("📱 مشاركة رقم الهاتف السوري", request_contact=True))
        bot.send_message(
            user_id,
            "⚠️ **اختبار الأمان (1/3)**:\nيرجى مشاركة رقم هاتفك السوري للاستمرار (يجب أن يبدأ بـ +963 أو 09):",
            reply_markup=kb, parse_mode="Markdown"
        )
        return

    # 2. القنوات الإجبارية
    if not check_sub(user_id):
        send_force_sub_msg(user_id)
        return

    # 3. اختبار الكابتشا (الفواكه)
    if not user['captcha_passed']:
        send_fruit_captcha(user_id)
        return

    # الواجهة الرئيسية
    bot.send_message(
        user_id,
        f"أهلاً بك **{message.from_user.first_name}** في البوت الرسمـي! 👋\nاختر من القائمة أدناه:",
        reply_markup=main_menu_keyboard(user_id),
        parse_mode="Markdown"
    )

# ==================== استقبال رقم الهاتف ====================
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    send_random_reaction(message.chat.id, message.message_id)
    user_id = message.from_user.id
    contact = message.contact
    
    if contact.user_id != user_id:
        bot.send_message(user_id, "❌ يرجى إرسال جهة الاتصال الخاصة بك فقط!")
        return

    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    # التحقق من أن الرقم سوري
    if not re.match(r'^(\+963|00963|09)\d{8,9}$', phone):
        bot.send_message(user_id, "❌ التسجيل متاح فقط للأرقام السورية (+963)!")
        return

    conn = get_db()
    conn.execute("UPDATE users SET phone=? WHERE user_id=?", (phone, user_id))
    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ تم إثبات رقم الهاتف بنجاح!", reply_markup=types.ReplyKeyboardRemove())
    start_cmd(message)

# ==================== اختبار الكابتشا والقنوات ====================
def send_force_sub_msg(user_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📢 قناة المبرمج (إجباري)", url=DEV_CHANNEL_URL))
    
    conn = get_db()
    channels = conn.execute("SELECT url FROM channels").fetchall()
    conn.close()
    
    for ch in channels:
        kb.add(types.InlineKeyboardButton("📢 قناة إضافية", url=ch['url']))
        
    kb.add(types.InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="verify_sub"))
    bot.send_message(user_id, "⚠️ **يجب عليك الاشتراك في القنوات التالية لاستخدام البوت:**", reply_markup=kb)

FRUITS = {'🍎': 'تفاح', '🍌': 'موز', '🍇': 'عنب', '🍊': 'برتقال'}

def send_fruit_captcha(user_id):
    target_emoji, target_name = random.choice(list(FRUITS.items()))
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    buttons = []
    for emoji, name in FRUITS.items():
        cb = f"captcha_correct_{user_id}" if emoji == target_emoji else f"captcha_wrong_{user_id}"
        buttons.append(types.InlineKeyboardButton(f"{emoji} {name}", callback_data=cb))
    
    random.shuffle(buttons)
    kb.add(*buttons)
    
    bot.send_message(user_id, f"🧩 **اختبار الأمان (اختيار الفاكهة)**:\nيرجى اختيار رمز: **{target_name} ({target_emoji})**", reply_markup=kb)

# ==================== معالجة أزرار Inline Callbacks ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    data = call.data

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    user = get_user(user_id)
    if not user:
        return

    # التحقق من الاشتراك
    if data == "verify_sub":
        if check_sub(user_id):
            bot.send_message(user_id, "✅ تم التحقق من الاشتراك بنجاح!")
            start_cmd(call.message)
        else:
            bot.send_message(user_id, "❌ لم تشترك في جميع القنوات بعد!")
        return

    # الكابتشا الصحيحة
    if data.startswith("captcha_correct_"):
        conn = get_db()
        conn.execute("UPDATE users SET captcha_passed=1 WHERE user_id=?", (user_id,))
        
        welcome_active = get_setting("welcome_bonus_active")
        welcome_amt = float(get_setting("welcome_bonus_amount"))
        if welcome_active == "1" and welcome_amt > 0:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (welcome_amt, user_id))
            bot.send_message(user_id, f"🎁 حصلت على بونص ترحيبي بقيمة {welcome_amt} NPS!")

        ref_id = user['referred_by']
        if ref_id:
            ref_reward = float(get_setting("ref_reward"))
            conn.execute("UPDATE users SET balance = balance + ?, referrals_count = referrals_count + 1 WHERE user_id=?", (ref_reward, ref_id))
            conn.commit()
            try:
                bot.send_message(ref_id, f"🎉 انضم شخص جديد عن طريق رابطك! حصلت على **{ref_reward} NPS**")
                bot.send_message(SUPER_ADMIN_ID, f"🔔 **إشعار إحالة**:\nالمستخدم: `{user_id}`\nعن طريق: `{ref_id}`", parse_mode="Markdown")
            except Exception:
                pass
        else:
            conn.commit()
            
        conn.close()
        bot.send_message(user_id, "✅ تم تخطي اختبار الأمان بنجاح!")
        start_cmd(call.message)
        return

    if data.startswith("captcha_wrong_"):
        bot.send_message(user_id, "❌ إجابة خاطئة! حاول مرة أخرى.")
        send_fruit_captcha(user_id)
        return

    # --- خدمات العميل ---
    if data == "user_balance":
        bot.send_message(user_id, f"💳 **رصيدك الحالي**: `{user['balance']}` NPS", parse_mode="Markdown")

    elif data == "user_withdraw":
        cooldown = int(get_setting("withdraw_cooldown_hours"))
        if user['last_withdraw']:
            last_w = datetime.datetime.strptime(user['last_withdraw'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_w).total_seconds() < cooldown * 3600:
                rem_hours = round(cooldown - (datetime.datetime.now() - last_w).total_seconds() / 3600, 1)
                bot.send_message(user_id, f"⏳ يمكنك السحب مرة كل {cooldown} ساعة. يتبقى لك: {rem_hours} ساعة.")
                return

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("سيريتل كاش", callback_data="withdraw_meth_syriatel"),
            types.InlineKeyboardButton("شام كاش", callback_data="withdraw_meth_sham")
        )
        bot.send_message(user_id, "اختر طريقة السحب المطلوبة:", reply_markup=kb)

    elif data.startswith("withdraw_meth_"):
        method = "سيريتل كاش" if "syriatel" in data else "شام كاش"
        m_key = "syriatel" if "syriatel" in data else "sham"
        min_w = float(get_setting(f"min_withdraw_{m_key}"))
        max_w = float(get_setting(f"max_withdraw_{m_key}"))

        msg = bot.send_message(
            user_id,
            f"طريقة السحب: **{method}**\n"
            f"الحد الأدنى: `{min_w}` - الحد الأقصى: `{max_w}`\n\n"
            f"أدخل مبلغ السحب المطلوب:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_withdraw_amount, m_key, min_w, max_w)

    elif data == "user_daily":
        cooldown_hours = 24
        if user['last_daily']:
            last_d = datetime.datetime.strptime(user['last_daily'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_d).total_seconds() < cooldown_hours * 3600:
                bot.send_message(user_id, "⏳ لقد حصلت على الهدية اليومية بالفعل! عد غداً.")
                return
        
        reward = float(get_setting("daily_reward"))
        update_balance(user_id, reward)
        conn = get_db()
        conn.execute("UPDATE users SET last_daily=? WHERE user_id=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"🎁 حصلت على هديتك اليومية بقيمة **{reward} NPS**!")

    elif data == "user_weekly":
        cooldown_hours = 168
        if user['last_weekly']:
            last_w = datetime.datetime.strptime(user['last_weekly'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_w).total_seconds() < cooldown_hours * 3600:
                bot.send_message(user_id, "⏳ لقد حصلت على الهدية الأسبوعية بالفعل! عد الأسبوع القادم.")
                return
        
        reward = float(get_setting("weekly_reward"))
        update_balance(user_id, reward)
        conn = get_db()
        conn.execute("UPDATE users SET last_weekly=? WHERE user_id=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"🏆 حصلت على هديتك الأسبوعية بقيمة **{reward} NPS**!")

    elif data == "user_promo":
        cooldown = int(get_setting("promo_cooldown_hours"))
        if user['last_promo']:
            last_p = datetime.datetime.strptime(user['last_promo'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_p).total_seconds() < cooldown * 3600:
                bot.send_message(user_id, f"⏳ يمكنك إدخال كود هدية كل {cooldown} ساعات مرة واحدة.")
                return

        msg = bot.send_message(user_id, "🎟 أدخل كود الهدية الآن:")
        bot.register_next_step_handler(msg, process_promo_code)

    elif data == "user_referral":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        ref_reward = get_setting("ref_reward")
        bot.send_message(
            user_id,
            f"🔗 **رابط إحالتك الخاص**:\n`{ref_link}`\n\n"
            f"👥 عدد إحالاتك: **{user['referrals_count']}**\n"
            f"💰 المكافأة لكل إحالة: **{ref_reward} NPS**\n"
            f"⚠️ يتم احتساب الإحالة فقط بعد تخطي اختبار الأمان برقم سوري.",
            parse_mode="Markdown"
        )

    elif data == "user_support":
        msg = bot.send_message(user_id, "💬 اكتب رسالتك للدعم الفني وسيتم الرد عليك في أقرب وقت:")
        bot.register_next_step_handler(msg, process_support_msg)

    # --- لوحة الإدارة ---
    elif data == "admin_panel" and is_admin(user_id):
        bot.send_message(user_id, "🛠 **لوحة التحكم بالبوت**:", reply_markup=admin_menu_keyboard(), parse_mode="Markdown")

    elif data == "adm_stats" and is_admin(user_id):
        conn = get_db()
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_balance = conn.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0
        conn.close()
        bot.send_message(user_id, f"📊 **إحصائيات البوت**:\n\n👥 عدد المستخدمين: `{total_users}`\n💰 إجمالي الأرصدة: `{total_balance}` NPS", parse_mode="Markdown")

    elif data == "adm_user_info" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل ID العميل المراد عرض تفاصيله:")
        bot.register_next_step_handler(msg, process_adm_user_info)

    elif data == "adm_add_admin" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل ID الأدمن الجديد:")
        bot.register_next_step_handler(msg, process_adm_add_admin)

    elif data == "adm_add_channel" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل معرف القناة ورابطها بالنمط التالي:\n`@channel_username https://t.me/channel_url`")
        bot.register_next_step_handler(msg, process_adm_add_channel)

    elif data == "adm_gen_code" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل بيانات الكود بالشكل التالي:\n`اسم_الكود القيمة عدد_الاستخدامات`\nمثال: `FREE50 10 100`")
        bot.register_next_step_handler(msg, process_gen_code)

    elif data == "adm_del_code" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل اسم الكود المراد إلغائه:")
        bot.register_next_step_handler(msg, process_adm_del_code)

    elif data == "adm_reset_balances" and is_admin(user_id):
        conn = get_db()
        conn.execute("UPDATE users SET balance = 0")
        conn.commit()
        conn.close()
        bot.send_message(user_id, "✅ تم تصفير جميع أرصدة المستخدمين بنجاح.")

    elif data == "adm_toggle_maint" and is_admin(user_id):
        curr = get_setting("maintenance_mode")
        new_val = "1" if curr == "0" else "0"
        set_setting("maintenance_mode", new_val)
        status = "مفعل 🛠" if new_val == "1" else "معطل ✅"
        bot.send_message(user_id, f"تم تغيير وضع الصيانة إلى: **{status}**")

    elif data == "adm_private_msg" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل ID المستخدم ثم النص بالنمط التالي:\n`user_id الرسالة`")
        bot.register_next_step_handler(msg, process_adm_private_msg)

    elif data == "adm_broadcast" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل نص الرسالة الجماعية التي ترغب بإرسالها لكافة العُملاء:")
        bot.register_next_step_handler(msg, process_adm_broadcast)

    elif data == "adm_settings_config" and is_admin(user_id):
        msg = bot.send_message(
            user_id,
            "⚙️ **تغيير الإعدادات**:\nأرسل مفتاح الإعداد والقيمة مفصولين بمسافة:\n\n"
            "المفاتيح المتاحة:\n"
            "`min_withdraw_syriatel`\n`max_withdraw_syriatel`\n`min_withdraw_sham`\n`max_withdraw_sham`\n"
            "`withdraw_cooldown_hours`\n`promo_cooldown_hours`\n`ref_reward`\n`daily_reward`\n`weekly_reward`\n\n"
            "مثال: `ref_reward 10`"
        )
        bot.register_next_step_handler(msg, process_adm_set_config)

    elif data == "adm_ban_user" and is_admin(user_id):
        msg = bot.send_message(user_id, "أدخل ID المستخدم لحظره أو إلغاء حظره:")
        bot.register_next_step_handler(msg, process_adm_ban_user)

    elif data == "adm_leaderboard" and is_admin(user_id):
        conn = get_db()
        top_users = conn.execute("SELECT user_id, first_name, balance, referrals_count FROM users ORDER BY balance DESC LIMIT 10").fetchall()
        conn.close()
        text = "🏆 **سجل أعلى اللاعبين رصيداً وإحالات**:\n\n"
        for idx, u in enumerate(top_users, 1):
            text += f"{idx}. {u['first_name']} (`{u['user_id']}`)\n   💰 الرصيد: `{u['balance']}` | 👥 الإحالات: `{u['referrals_count']}`\n"
        bot.send_message(user_id, text, parse_mode="Markdown")

    elif data.startswith("reply_supp_") and is_admin(user_id):
        target_uid = data.split("_")[2]
        msg = bot.send_message(user_id, f"اكتب الرد الموجه للعميل `{target_uid}`:")
        bot.register_next_step_handler(msg, process_reply_support, target_uid)

# ==================== المعالجات المتسلسلة (Next Step Handlers) ====================
def process_withdraw_amount(message, m_key, min_w, max_w):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        user = get_user(user_id)
        
        if amount < min_w or amount > max_w:
            bot.send_message(user_id, f"❌ المبلغ خارج الحدود المسموحة ({min_w} - {max_w}). تم إلغاء العملية.")
            return

        if user['balance'] < amount:
            bot.send_message(user_id, "❌ رصيدك الحالي غير كافٍ إجراء هذه العملية.")
            return

        msg = bot.send_message(user_id, "أدخل رقم الحساب/الهاتف لتحويل الرصيد عليه:")
        bot.register_next_step_handler(msg, process_withdraw_account, amount)

    except ValueError:
        bot.send_message(user_id, "❌ قيمة غير صالحة. تم إلغاء السحب.")

def process_withdraw_account(message, amount):
    user_id = message.from_user.id
    acc_num = message.text
    
    update_balance(user_id, -amount)
    conn = get_db()
    conn.execute("UPDATE users SET last_withdraw=?, withdrawals_count=withdrawals_count+1 WHERE user_id=?", 
                 (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ تم إرسال طلب السحب بنجاح للمراجعة!")
    bot.send_message(
        SUPER_ADMIN_ID,
        f"🚨 **طلب سحب جديد**:\nالمستخدم: `{user_id}`\nالمبلغ: `{amount}` NPS\nالحساب: `{acc_num}`",
        parse_mode="Markdown"
    )

def process_promo_code(message):
    user_id = message.from_user.id
    code_text = message.text.strip()
    
    conn = get_db()
    code = conn.execute("SELECT * FROM promo_codes WHERE code=? AND is_active=1", (code_text,)).fetchone()
    
    if not code or code['current_uses'] >= code['max_uses']:
        bot.send_message(user_id, "❌ الكود غير صحيح أو انتهت صلاحيته.")
        conn.close()
        return

    reward = code['reward']
    conn.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code=?", (code_text,))
    conn.execute("UPDATE users SET last_promo=? WHERE user_id=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()

    update_balance(user_id, reward)
    bot.send_message(user_id, f"🎉 تم تفعيل الكود بنجاح! حصلت على **{reward} NPS**")
    bot.send_message(SUPER_ADMIN_ID, f"🔔 المستخدم `{user_id}` استخدم الكود `{code_text}`")

def process_support_msg(message):
    user_id = message.from_user.id
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("رد على العميل", callback_data=f"reply_supp_{user_id}"))
    
    bot.send_message(SUPER_ADMIN_ID, f"📩 **رسالة دعم من** `{user_id}`:\n\n{message.text}", reply_markup=kb, parse_mode="Markdown")
    bot.send_message(user_id, "✅ تم إرسال رسالتك لفريق الدعم.")

def process_reply_support(message, target_uid):
    try:
        bot.send_message(target_uid, f"💬 **رد من فريق الدعم**:\n\n{message.text}")
        bot.send_message(message.chat.id, "✅ تم إرسال الرد بنجاح.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل الإرسال: {e}")

def process_gen_code(message):
    try:
        parts = message.text.split()
        code, reward, max_uses = parts[0], float(parts[1]), int(parts[2])
        
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO promo_codes (code, reward, max_uses) VALUES (?, ?, ?)", (code, reward, max_uses))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"✅ تم إنشاء الكود `{code}` بنجاح!", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ بتنسيق البيانات: {e}")

def process_adm_user_info(message):
    try:
        uid = int(message.text.strip())
        u = get_user(uid)
        if not u:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود بالبيانات.")
            return
        
        text = (
            f"👤 **تفاصيل العميل** `{uid}`:\n\n"
            f"الاسم: {u['first_name']}\n"
            f"المعرف: @{u['username']}\n"
            f"الرقم: `{u['phone']}`\n"
            f"الرصيد: `{u['balance']}` NPS\n"
            f"عدد الإحالات: `{u['referrals_count']}`\n"
            f"مرات السحب: `{u['withdrawals_count']}`\n"
            f"المُحيل: `{u['referred_by']}`"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ في إدخال ID.")

def process_adm_add_admin(message):
    try:
        uid = int(message.text.strip())
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم إسناد صلاحيات الأدمن لـ `{uid}` بنجاح.")
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ في إدخال ID.")

def process_adm_add_channel(message):
    try:
        parts = message.text.split()
        ch_id, ch_url = parts[0], parts[1]
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO channels (channel_id, url) VALUES (?, ?)", (ch_id, ch_url))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ تم إضافة القناة `{ch_id}` بنجاح.")
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ بالتنسيق.")

def process_adm_del_code(message):
    code_text = message.text.strip()
    conn = get_db()
    conn.execute("UPDATE promo_codes SET is_active=0 WHERE code=?", (code_text,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, f"✅ تم إلغاء الكود `{code_text}`.")

def process_adm_private_msg(message):
    try:
        parts = message.text.split(maxsplit=1)
        uid, txt = int(parts[0]), parts[1]
        bot.send_message(uid, f"📩 **رسالة خاصة من الإدارة**:\n\n{txt}")
        bot.send_message(message.chat.id, "✅ تم الإرسال بنجاح.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

def process_adm_broadcast(message):
    txt = message.text
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    
    count = 0
    for u in users:
        try:
            bot.send_message(u['user_id'], f"📢 **تنويه جماعي**:\n\n{txt}")
            count += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ تم إرسال الإذاعة إلى `{count}` مستخدم.")

def process_adm_set_config(message):
    try:
        parts = message.text.split()
        k, v = parts[0], parts[1]
        set_setting(k, v)
        bot.send_message(message.chat.id, f"✅ تم ضبط `{k}` على القيمة `{v}`.")
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ في التنسيق.")

def process_adm_ban_user(message):
    try:
        uid = int(message.text.strip())
        u = get_user(uid)
        if not u:
            bot.send_message(message.chat.id, "❌ المستخدم غير موجود.")
            return
        new_ban = 0 if u['is_banned'] else 1
        conn = get_db()
        conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new_ban, uid))
        conn.commit()
        conn.close()
        st = "حظر" if new_ban else "إلغاء حظر"
        bot.send_message(message.chat.id, f"✅ تم {st} المستخدم `{uid}`.")
    except Exception:
        bot.send_message(message.chat.id, "❌ خطأ في ID.")

# ==================== نظام الإخصام عند مغادرة القنوات ====================
@bot.chat_member_handler()
def handle_chat_member(update):
    if update.new_chat_member.status in ['left', 'kicked']:
        user_id = update.new_chat_member.user.id
        u = get_user(user_id)
        if u:
            update_balance(user_id, -3)
            try:
                bot.send_message(user_id, "⚠️ تم خصم **3 NPS** من رصيدك بسبب مغادرتك إحدى القنوات الإجبارية!")
            except Exception:
                pass
            
            ref_id = u['referred_by']
            if ref_id:
                update_balance(ref_id, -3)
                try:
                    bot.send_message(ref_id, f"⚠️ تم خصم **3 NPS** من رصيدك بسبب مغادرة المستخدم الذي قمت بإحالته (`{user_id}`) للقناة!")
                except Exception:
                    pass

# ==================== استقبال كافة الرسائل العادية والتفاعل ====================
@bot.message_handler(func=lambda m: True)
def auto_reaction_handler(message):
    send_random_reaction(message.chat.id, message.message_id)

# ==================== تشغيل التطبيق ====================
if __name__ == "__main__":
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    print("Bot starting polling...")
    bot.infinity_polling(skip_pending=True, allowed_updates=telebot.util.update_types)

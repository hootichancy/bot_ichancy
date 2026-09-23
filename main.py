import os
import re
import sqlite3
import random
import datetime
import telebot
from telebot import types

# ==================== البيانات الأساسية ====================
BOT_TOKEN = "8776743286:AAFlC0xFDGNtP1ZqwcLP_jLxf_M6Jd_joVQ"
SUPER_ADMIN_ID = 8577656131
DEV_CHANNEL_URL = "https://t.me/lerafree"
DEV_CHANNEL_USERNAME = "lerafree"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# أسماء الإعدادات باللغة العربية للوحة التحكم
CONFIG_LABELS = {
    "min_withdraw_syriatel": "الحد الأدنى لسحب سيريتل كاش",
    "max_withdraw_syriatel": "الحد الأقصى لسحب سيريتل كاش",
    "min_withdraw_sham": "الحد الأدنى لسحب شام كاش",
    "max_withdraw_sham": "الحد الأقصى لسحب شام كاش",
    "withdraw_cooldown_hours": "مدة انتظار السحب (بالساعات)",
    "promo_cooldown_hours": "مدة انتظار الأكواد (بالساعات)",
    "ref_reward": "مكافأة الإحالة",
    "daily_reward": "مكافأة الهدية اليومية",
    "weekly_reward": "مكافأة الهدية الأسبوعية"
}

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
            name TEXT,
            url TEXT
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE channels ADD COLUMN name TEXT")
    except sqlite3.OperationalError:
        pass
    
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

# ==================== التفاعل التلقائي ====================
REACTIONS = ['👍', '❤️', '🔥', '👏', '🎉', '⚡️', '🤩', '👌']

def send_random_reaction(chat_id, message_id):
    try:
        emoji = random.choice(REACTIONS)
        bot.set_message_reaction(chat_id, message_id, [types.ReactionTypeEmoji(emoji)])
    except Exception:
        pass

# ==================== التحقق من القنوات والأمان ====================
def check_sub(user_id):
    try:
        member = bot.get_chat_member(f"@{DEV_CHANNEL_USERNAME}", user_id)
        if member.status in ['left', 'kicked']:
            return False
    except Exception:
        pass

    conn = get_db()
    channels = conn.execute("SELECT channel_id FROM channels").fetchall()
    conn.close()
    
    for ch in channels:
        try:
            member = bot.get_chat_member(ch['channel_id'], user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception:
            return False
    return True

def send_force_sub_msg(user_id):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📢 قناة المبرمج (إجباري)", url=DEV_CHANNEL_URL))
    
    conn = get_db()
    channels = conn.execute("SELECT * FROM channels").fetchall()
    conn.close()
    
    for ch in channels:
        ch_title = ch['name'] if ch['name'] else f"قناة: {ch['channel_id']}"
        kb.add(types.InlineKeyboardButton(f"📢 {ch_title}", url=ch['url']))
        
    kb.add(types.InlineKeyboardButton("✅ تحقق من الاشتراك الآن", callback_data="verify_sub"))
    
    text = (
        "⚠️ <b>تنبيه هام للاستمرار:</b>\n\n"
        "يجب عليك الاشتراك في القنوات الرسمية التالية لتتمكن من استخدام البوت والحصول على مكافآتك:"
    )
    bot.send_message(user_id, text, reply_markup=kb)

# ==================== القوائم والأزرار المحدثة والمكبرة ====================
def main_menu_keyboard(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("💰 رصيدي الشخصي", callback_data="user_balance"),
        types.InlineKeyboardButton("💳 طلب سحب رصيد", callback_data="user_withdraw")
    )
    kb.add(
        types.InlineKeyboardButton("🎁 الهدية اليومية", callback_data="user_daily"),
        types.InlineKeyboardButton("🏆 الهدية الأسبوعية", callback_data="user_weekly")
    )
    kb.add(
        types.InlineKeyboardButton("🎟 إدخال كود هدية", callback_data="user_promo"),
        types.InlineKeyboardButton("🔗 رابط إحالتك", callback_data="user_referral")
    )
    kb.add(
        types.InlineKeyboardButton("📢 قناة المبرمج", url=DEV_CHANNEL_URL),
        types.InlineKeyboardButton("💬 الدعم الفني", callback_data="user_support")
    )
    if is_admin(user_id):
        kb.add(types.InlineKeyboardButton("⚙️ لوحة التحكم الاحترافية", callback_data="admin_panel"))
    return kb

def admin_menu_keyboard():
    maint_status = "مفعل 🟢" if get_setting("maintenance_mode") == "1" else "معطل 🔴"
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 إدارة سجل العملاء", callback_data="adm_users_menu"),
        types.InlineKeyboardButton("⚙️ إعدادات الأسعار والحدود", callback_data="adm_settings_menu")
    )
    kb.add(
        types.InlineKeyboardButton("📢 إدارة القنوات الإجبارية", callback_data="adm_channels_menu"),
        types.InlineKeyboardButton("🎟 إدارة أكواد المكافآت", callback_data="adm_promo_menu")
    )
    kb.add(
        types.InlineKeyboardButton("✉️ إرسال رسالة خاصة", callback_data="adm_private_msg"),
        types.InlineKeyboardButton("📢 إرسال إذاعة جماعية", callback_data="adm_broadcast")
    )
    kb.add(
        types.InlineKeyboardButton(f"🛠 وضع الصيانة: {maint_status}", callback_data="adm_toggle_maint_fast"),
        types.InlineKeyboardButton("📊 الإحصائيات الشاملة", callback_data="adm_stats")
    )
    kb.add(
        types.InlineKeyboardButton("🏆 سجل المميزين (Top 10)", callback_data="adm_leaderboard"),
        types.InlineKeyboardButton("🔄 تصفير كافة الأرصدة", callback_data="adm_reset_balances")
    )
    kb.add(
        types.InlineKeyboardButton("➕ إضافة أدمن جديد", callback_data="adm_add_admin")
    )
    kb.add(
        types.InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="user_main_menu")
    )
    return kb

def admin_users_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔍 عرض تفاصيل عميل", callback_data="adm_user_info"),
        types.InlineKeyboardButton("🚫 حظر / إلغاء حظر عميل", callback_data="adm_ban_user")
    )
    kb.add(types.InlineKeyboardButton("🔙 رجوع للوحة الإدارة", callback_data="admin_panel"))
    return kb

def admin_settings_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("💵 حد أدنى سيريتل", callback_data="set_cfg_min_withdraw_syriatel"),
        types.InlineKeyboardButton("💵 حد أقصى سيريتل", callback_data="set_cfg_max_withdraw_syriatel")
    )
    kb.add(
        types.InlineKeyboardButton("🪙 حد أدنى شام", callback_data="set_cfg_min_withdraw_sham"),
        types.InlineKeyboardButton("🪙 حد أقصى شام", callback_data="set_cfg_max_withdraw_sham")
    )
    kb.add(
        types.InlineKeyboardButton("⏳ انتظار السحب (ساعات)", callback_data="set_cfg_withdraw_cooldown_hours"),
        types.InlineKeyboardButton("⏳ انتظار الكود (ساعات)", callback_data="set_cfg_promo_cooldown_hours")
    )
    kb.add(
        types.InlineKeyboardButton("👥 مكافأة الإحالة", callback_data="set_cfg_ref_reward"),
        types.InlineKeyboardButton("🎁 الهدية اليومية", callback_data="set_cfg_daily_reward")
    )
    kb.add(
        types.InlineKeyboardButton("🏆 الهدية الأسبوعية", callback_data="set_cfg_weekly_reward")
    )
    kb.add(types.InlineKeyboardButton("🔙 رجوع للوحة الإدارة", callback_data="admin_panel"))
    return kb

def admin_channels_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    conn = get_db()
    channels = conn.execute("SELECT * FROM channels").fetchall()
    conn.close()
    
    for ch in channels:
        name_disp = ch['name'] if ch['name'] else ch['channel_id']
        kb.add(types.InlineKeyboardButton(f"❌ حذف: {name_disp}", callback_data=f"adm_del_chan_{ch['channel_id']}"))
        
    kb.add(types.InlineKeyboardButton("➕ إضافة قناة جديد", callback_data="adm_add_channel"))
    kb.add(types.InlineKeyboardButton("🔙 رجوع للوحة الإدارة", callback_data="admin_panel"))
    return kb

def admin_promo_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    conn = get_db()
    codes = conn.execute("SELECT * FROM promo_codes WHERE is_active=1").fetchall()
    conn.close()
    
    for c in codes:
        kb.add(types.InlineKeyboardButton(f"🎟 {c['code']} ({c['reward']} NPS) | [{c['current_uses']}/{c['max_uses']}] ❌ إلغاء", callback_data=f"adm_del_code_fast_{c['code']}"))
        
    kb.add(types.InlineKeyboardButton("✨ توليد كود جديد احترافي", callback_data="adm_gen_code"))
    kb.add(types.InlineKeyboardButton("🔙 رجوع للوحة الإدارة", callback_data="admin_panel"))
    return kb

# ==================== اختبار الكابتشا ====================
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
    
    text = f"🧩 <b>اختبار الأمان الذكي (اختيار الفاكهة):</b>\n\nيرجى اختيار الرمز المناسب لـ: <b>{target_name} ({target_emoji})</b>"
    bot.send_message(user_id, text, reply_markup=kb)

# ==================== المعالجة الرئيسية /start ====================
@bot.message_handler(commands=['start'])
def start_cmd(message):
    send_random_reaction(message.chat.id, message.message_id)
    user_id = message.from_user.id
    
    if get_setting("maintenance_mode") == "1" and not is_admin(user_id):
        bot.send_message(user_id, "⚠️ <b>البوت حالياً في وضع الصيانة والتطوير، يرجى المحاولة لاحقاً.</b>")
        return

    conn = get_db()
    user = get_user(user_id)
    
    args = message.text.split()
    ref_by = int(args[1]) if len(args) > 1 and args[1].isdigit() and int(args[1]) != user_id else None

    is_new = False
    if not user:
        is_new = True
        conn.execute(
            "INSERT INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)",
            (user_id, message.from_user.username, message.from_user.first_name, ref_by)
        )
        conn.commit()
    conn.close()

    user = get_user(user_id)
    if user['is_banned']:
        bot.send_message(user_id, "❌ <b>عذراً، حسابك محظور حالياً من استخدام البوت.</b>")
        return

    # إشعار للمُحيل عند دخول لاعب جديد
    if is_new and ref_by:
        try:
            bot.send_message(ref_by, f"🔔 <b>إشعار انضمام:</b> انضم مستخدم جديد عبر رابطك (<code>{user_id}</code>)، وهو في طور إكمال الاختبارات!")
        except Exception:
            pass

    # --- تسلسل الأمان التلقائي ---
    # الخطوة 1: مشاركة رقم الهاتف
    if not user['phone']:
        kb = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        kb.add(types.KeyboardButton("📱 مشاركة رقم الهاتف السوري", request_contact=True))
        text = (
            "⚠️ <b>خطوة أمان إجبارية (1/3):</b>\n\n"
            "يرجى الضغط على الزر أدناه لمشاركة رقم هاتفك السوري للاستمرار (+963 / 09):"
        )
        bot.send_message(user_id, text, reply_markup=kb)
        return

    # الخطوة 2: اختبار الكابتشا
    if not user['captcha_passed']:
        send_fruit_captcha(user_id)
        return

    # الخطوة 3: التحقق من القنوات الإجبارية
    if not check_sub(user_id):
        send_force_sub_msg(user_id)
        return

    # القائمة الرئيسية
    welcome_text = (
        f"أهلاً ومرحباً بك <b>{message.from_user.first_name}</b> في البوت الرسمي! 👋✨\n\n"
        f"اختر الخدمة المطلوبة من القائمة التفاعلية أدناه:"
    )
    bot.send_message(user_id, welcome_text, reply_markup=main_menu_keyboard(user_id))

# ==================== استقبال رقم الهاتف ====================
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    send_random_reaction(message.chat.id, message.message_id)
    user_id = message.from_user.id
    contact = message.contact
    
    if contact.user_id != user_id:
        bot.send_message(user_id, "❌ <b>يرجى مشاركة جهة الاتصال الخاصة بك أنت فقط!</b>")
        return

    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    if not re.match(r'^(\+963|00963|09)\d{8,9}$', phone):
        bot.send_message(user_id, "❌ <b>التسجيل متاح فقط للأرقام السورية الرسمية (+963)!</b>")
        return

    conn = get_db()
    conn.execute("UPDATE users SET phone=? WHERE user_id=?", (phone, user_id))
    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ <b>تم إثبات رقم الهاتف بنجاح!</b>", reply_markup=types.ReplyKeyboardRemove())
    send_fruit_captcha(user_id)

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

    # زر التحقق من الاشتراك بالقنوات
    if data == "verify_sub":
        if check_sub(user_id):
            bot.send_message(user_id, "✅ <b>تم التحقق من جميع الاشتراكات بنجاح!</b>")
            start_cmd(call.message)
        else:
            bot.send_message(user_id, "❌ <b>لم تشترك بعد في جميع القنوات المطلوبة! اشترك واضغط مجدداً.</b>")
            send_force_sub_msg(user_id)
        return

    # تحقق عام من القنوات قبل أداء أي خدمة للعملاء
    if not is_admin(user_id) and not check_sub(user_id):
        send_force_sub_msg(user_id)
        return

    # معالجة اجتياز الكابتشا
    if data.startswith("captcha_correct_"):
        conn = get_db()
        conn.execute("UPDATE users SET captcha_passed=1 WHERE user_id=?", (user_id,))
        
        welcome_active = get_setting("welcome_bonus_active")
        welcome_amt = float(get_setting("welcome_bonus_amount"))
        if welcome_active == "1" and welcome_amt > 0:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (welcome_amt, user_id))
            bot.send_message(user_id, f"🎁 <b>مبروك! حصلت على مكافأة ترحيبية بقيمة {welcome_amt} NPS!</b>")

        ref_id = user['referred_by']
        if ref_id:
            ref_reward = float(get_setting("ref_reward"))
            conn.execute("UPDATE users SET balance = balance + ?, referrals_count = referrals_count + 1 WHERE user_id=?", (ref_reward, ref_id))
            conn.commit()
            try:
                bot.send_message(ref_id, f"🎉 <b>مبروك!</b> اجتاز صديقك اختبار الأمان وحصلت على <b>{ref_reward} NPS</b>!")
                bot.send_message(SUPER_ADMIN_ID, f"🔔 <b>إشعار إحالة ناجحة:</b>\nالمستخدم: <code>{user_id}</code>\nبواسطة: <code>{ref_id}</code>")
            except Exception:
                pass
        else:
            conn.commit()
            
        conn.close()
        bot.send_message(user_id, "✅ <b>تم تخطي اختبار الأمان بنجاح!</b>")
        
        if not check_sub(user_id):
            send_force_sub_msg(user_id)
        else:
            start_cmd(call.message)
        return

    if data.startswith("captcha_wrong_"):
        bot.send_message(user_id, "❌ <b>إجابة خاطئة! حاول اختيار الرمز الصحيح مرة أخرى.</b>")
        send_fruit_captcha(user_id)
        return

    # --- خدمات المستخدم ---
    if data == "user_main_menu":
        bot.edit_message_text("📱 <b>القائمة الرئيسية للبوت:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=main_menu_keyboard(user_id))

    elif data == "user_balance":
        bot.send_message(user_id, f"💰 <b>رصيدك الحالي المتاح:</b> <code>{user['balance']}</code> NPS")

    elif data == "user_withdraw":
        cooldown = int(get_setting("withdraw_cooldown_hours"))
        if user['last_withdraw']:
            last_w = datetime.datetime.strptime(user['last_withdraw'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_w).total_seconds() < cooldown * 3600:
                rem_hours = round(cooldown - (datetime.datetime.now() - last_w).total_seconds() / 3600, 1)
                bot.send_message(user_id, f"⏳ <b>تنبيه السحب:</b> يمكنك السحب مرة كل {cooldown} ساعة.\nالمتبقي لك: <b>{rem_hours} ساعة</b>.")
                return

        kb = types.InlineKeyboardMarkup(row_width=2)
        kb.add(
            types.InlineKeyboardButton("📱 سيريتل كاش", callback_data="withdraw_meth_syriatel"),
            types.InlineKeyboardButton("🪙 شام كاش", callback_data="withdraw_meth_sham")
        )
        bot.send_message(user_id, "💳 <b>اختر طريقة السحب المفضلة لديك:</b>", reply_markup=kb)

    elif data.startswith("withdraw_meth_"):
        method = "سيريتل كاش" if "syriatel" in data else "شام كاش"
        m_key = "syriatel" if "syriatel" in data else "sham"
        min_w = float(get_setting(f"min_withdraw_{m_key}"))
        max_w = float(get_setting(f"max_withdraw_{m_key}"))

        text = (
            f"💳 <b>طريقة السحب المختارة: {method}</b>\n\n"
            f"🔸 الحد الأدنى: <code>{min_w}</code> NPS\n"
            f"🔹 الحد الأقصى: <code>{max_w}</code> NPS\n\n"
            f"✏️ <b>يرجى إرسال المبلغ المراد سحبه الآن:</b>"
        )
        msg = bot.send_message(user_id, text)
        bot.register_next_step_handler(msg, process_withdraw_amount, m_key, min_w, max_w)

    elif data == "user_daily":
        cooldown_hours = 24
        if user['last_daily']:
            last_d = datetime.datetime.strptime(user['last_daily'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_d).total_seconds() < cooldown_hours * 3600:
                bot.send_message(user_id, "⏳ <b>لقد استلمت الهداية اليومية بالفعل! عد غداً للحصول عليها مجدداً.</b>")
                return
        
        reward = float(get_setting("daily_reward"))
        update_balance(user_id, reward)
        conn = get_db()
        conn.execute("UPDATE users SET last_daily=? WHERE user_id=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"🎁 <b>مبروك! حصلت على هديتك اليومية بقيمة {reward} NPS!</b>")

    elif data == "user_weekly":
        cooldown_hours = 168
        if user['last_weekly']:
            last_w = datetime.datetime.strptime(user['last_weekly'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_w).total_seconds() < cooldown_hours * 3600:
                bot.send_message(user_id, "⏳ <b>لقد استلمت الهداية الأسبوعية بالفعل! عد الأسبوع القادم.</b>")
                return
        
        reward = float(get_setting("weekly_reward"))
        update_balance(user_id, reward)
        conn = get_db()
        conn.execute("UPDATE users SET last_weekly=? WHERE user_id=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"🏆 <b>مبروك! حصلت على هديتك الأسبوعية بقيمة {reward} NPS!</b>")

    elif data == "user_promo":
        cooldown = int(get_setting("promo_cooldown_hours"))
        if user['last_promo']:
            last_p = datetime.datetime.strptime(user['last_promo'], '%Y-%m-%d %H:%M:%S')
            if (datetime.datetime.now() - last_p).total_seconds() < cooldown * 3600:
                bot.send_message(user_id, f"⏳ <b>تنبيه الأكواد:</b> يمكنك تفعيل كود كل {cooldown} ساعات مرة واحدة.")
                return

        msg = bot.send_message(user_id, "🎟 <b>أدخل كود الهدية الخاص بك الآن:</b>")
        bot.register_next_step_handler(msg, process_promo_code)

    elif data == "user_referral":
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        ref_reward = get_setting("ref_reward")
        text = (
            f"🔗 <b>رابط إحالتك الخاص لتجميع الأرباح:</b>\n"
            f"<code>{ref_link}</code>\n\n"
            f"👥 عدد إحالاتك الناجحة: <b>{user['referrals_count']}</b>\n"
            f"💰 المكافأة لكل إحالة: <b>{ref_reward} NPS</b>\n\n"
            f"⚠️ يتم احتساب المكافأة فور توثيق صديقك لركم هاتفه واجتيازه الكابتشا."
        )
        bot.send_message(user_id, text)

    elif data == "user_support":
        msg = bot.send_message(user_id, "💬 <b>اكتب رسالتك لفريق الدعم وسنقوم بالرد عليك في أسرع وقت ممكن:</b>")
        bot.register_next_step_handler(msg, process_support_msg)

    # --- التعامل مع موافقة / رفض طلبات السحب من المشرف ---
    elif data.startswith("app_wd_") or data.startswith("rej_wd_"):
        if not is_admin(user_id):
            return
        
        parts = data.split("_")
        action = parts[0] # app or rej
        target_uid = int(parts[2])
        amount = float(parts[3])

        if action == "app":
            try:
                bot.edit_message_text(
                    f"✅ <b>تمت الموافقة على طلب السحب!</b>\n\n"
                    f"👤 العميل: <code>{target_uid}</code>\n"
                    f"💰 المبلغ: <code>{amount}</code> NPS\n"
                    f"👨‍💼 بواسطة المشرف: <code>{user_id}</code>",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
                bot.send_message(target_uid, f"🎉 <b>تهانينا!</b> تم قبول طلب سحب الرصيد الخاص بك بمبلغ <b>{amount} NPS</b> وتحويل المبلغ بنجاح!")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ خطأ عند تحديث الطلب: {e}")

        elif action == "rej":
            update_balance(target_uid, amount) # إعادة الرصيد المخصوم
            try:
                bot.edit_message_text(
                    f"❌ <b>تم رفض طلب السحب وإعادة الرصيد للحساب!</b>\n\n"
                    f"👤 العميل: <code>{target_uid}</code>\n"
                    f"💰 المبلغ المسترجع: <code>{amount}</code> NPS\n"
                    f"👨‍💼 بواسطة المشرف: <code>{user_id}</code>",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id
                )
                bot.send_message(target_uid, f"❌ <b>تنبيه:</b> تم رفض طلب سحب الرصيد الخاص بك بمبلغ <b>{amount} NPS</b>، وتمت إعادة الرصيد إلى حسابك تلقائياً.")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"❌ خطأ عند تحديث الطلب: {e}")

    # --- لوحة الإدارة الاحترافية ---
    elif is_admin(user_id):
        if data == "admin_panel":
            bot.edit_message_text("🛠 <b>لوحة التحكم الرئيسية بالإدارة:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_menu_keyboard())

        elif data == "adm_users_menu":
            bot.edit_message_text("👥 <b>قسم إدارة واستعلامات سجل العملاء:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_users_menu_keyboard())

        elif data == "adm_settings_menu":
            bot.edit_message_text("⚙️ <b>إعدادات الأسعار والحدود والخيارات:</b>\nاختر الخيار المراد تعديل قيمته مباشرة:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_settings_menu_keyboard())

        elif data == "adm_channels_menu":
            bot.edit_message_text("📢 <b>قسم إدارة القنوات الإجبارية:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_channels_menu_keyboard())

        elif data == "adm_promo_menu":
            bot.edit_message_text("🎟 <b>قسم إدارة أكواد الهدايا والمكافآت:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_promo_menu_keyboard())

        elif data == "adm_toggle_maint_fast":
            curr = get_setting("maintenance_mode")
            new_val = "1" if curr == "0" else "0"
            set_setting("maintenance_mode", new_val)
            bot.edit_message_text("🛠 <b>لوحة التحكم الرئيسية بالإدارة:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_menu_keyboard())

        elif data.startswith("set_cfg_"):
            cfg_key = data.replace("set_cfg_", "")
            curr_val = get_setting(cfg_key)
            label_name = CONFIG_LABELS.get(cfg_key, cfg_key)
            msg = bot.send_message(user_id, f"📌 <b>تعديل {label_name}</b>\nالقيمة الحالية هي: <code>{curr_val}</code>\n\nأدخل القيمة الجديدة الآن:")
            bot.register_next_step_handler(msg, process_single_setting_update, cfg_key, label_name)

        elif data.startswith("adm_del_chan_"):
            ch_id = data.replace("adm_del_chan_", "")
            conn = get_db()
            conn.execute("DELETE FROM channels WHERE channel_id=?", (ch_id,))
            conn.commit()
            conn.close()
            bot.edit_message_text("📢 <b>قسم إدارة القنوات الإجبارية:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_channels_menu_keyboard())

        elif data.startswith("adm_del_code_fast_"):
            code_text = data.replace("adm_del_code_fast_", "")
            conn = get_db()
            conn.execute("UPDATE promo_codes SET is_active=0 WHERE code=?", (code_text,))
            conn.commit()
            conn.close()
            bot.edit_message_text("🎟 <b>قسم إدارة أكواد الهدايا والمكافآت:</b>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=admin_promo_menu_keyboard())

        elif data == "adm_stats":
            conn = get_db()
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_balance = conn.execute("SELECT SUM(balance) FROM users").fetchone()[0] or 0
            conn.close()
            text = (
                f"📊 <b>إحصائيات البوت الشاملة واللحظية:</b>\n\n"
                f"👥 إجمالي عدد المستخدمين: <code>{total_users}</code>\n"
                f"💰 إجمالي أرصدة المستخدمين: <code>{total_balance}</code> NPS"
            )
            bot.send_message(user_id, text)

        elif data == "adm_user_info":
            msg = bot.send_message(user_id, "🔍 <b>أدخل آيدي (ID) العميل المراد الاستعلام عن تفاصيله:</b>")
            bot.register_next_step_handler(msg, process_adm_user_info)

        elif data == "adm_add_admin":
            msg = bot.send_message(user_id, "➕ <b>أدخل آيدي (ID) المشرف الجديد لمنحه الصلاحيات الكاملة:</b>")
            bot.register_next_step_handler(msg, process_adm_add_admin)

        elif data == "adm_add_channel":
            msg = bot.send_message(
                user_id,
                "1️⃣ <b>الخطوة الأولى:</b> أرسل <b>معرف القناة</b> أو הـ ID الخاص بها:\n(مثال: <code>@mychannel</code> أو <code>-100123456789</code>)"
            )
            bot.register_next_step_handler(msg, process_adm_add_channel_step1)

        elif data == "adm_gen_code":
            text = (
                "✨ <b>إنشاء كود مكافأة جديد:</b>\n\n"
                "أرسل البيانات بالنمط التالي:\n"
                "<code>اسم_الكود القيمة عدد_الاستخدامات</code>\n\n"
                "مثال: <code>FREE100 10 50</code>"
            )
            msg = bot.send_message(user_id, text)
            bot.register_next_step_handler(msg, process_gen_code)

        elif data == "adm_reset_balances":
            conn = get_db()
            conn.execute("UPDATE users SET balance = 0")
            conn.commit()
            conn.close()
            bot.send_message(user_id, "✅ <b>تم تصفير جميع أرصدة المستخدمين بنجاح.</b>")

        elif data == "adm_private_msg":
            msg = bot.send_message(user_id, "✉️ <b>أدخل آيدي المستخدم ثم النص بالشكل التالي:</b>\n<code>user_id الرسالة</code>")
            bot.register_next_step_handler(msg, process_adm_private_msg)

        elif data == "adm_broadcast":
            msg = bot.send_message(user_id, "📢 <b>أدخل نص الرسالة الجماعية المراد إرسالها لجميع العملاء:</b>")
            bot.register_next_step_handler(msg, process_adm_broadcast)

        elif data == "adm_ban_user":
            msg = bot.send_message(user_id, "🚫 <b>أدخل آيدي المستخدم لحظره أو إلغاء حظره:</b>")
            bot.register_next_step_handler(msg, process_adm_ban_user)

        elif data == "adm_leaderboard":
            conn = get_db()
            top_users = conn.execute("SELECT user_id, first_name, balance, referrals_count FROM users ORDER BY balance DESC LIMIT 10").fetchall()
            conn.close()
            text = "🏆 <b>سجل أعلى 10 لاعبين رصيداً وإحالات:</b>\n\n"
            for idx, u in enumerate(top_users, 1):
                text += f"{idx}. {u['first_name']} (<code>{u['user_id']}</code>)\n   💰 الرصيد: <code>{u['balance']}</code> NPS | 👥 الإحالات: <code>{u['referrals_count']}</code>\n"
            bot.send_message(user_id, text)

        elif data.startswith("reply_supp_"):
            target_uid = data.split("_")[2]
            msg = bot.send_message(user_id, f"💬 <b>اكتب الرد الموجه للعميل <code>{target_uid}</code>:</b>")
            bot.register_next_step_handler(msg, process_reply_support, target_uid)

# ==================== المعالجات المتسلسلة (Next Step Handlers) ====================
def process_single_setting_update(message, key, label_name):
    try:
        val = message.text.strip()
        set_setting(key, val)
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔙 رجوع للإعدادات", callback_data="adm_settings_menu"))
        bot.send_message(message.chat.id, f"✅ <b>تم تحديث {label_name} إلى:</b> <code>{val}</code> بنجاح!", reply_markup=kb)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

# --- إضافة قناة تفاعلية ---
def process_adm_add_channel_step1(message):
    ch_id = message.text.strip()
    msg = bot.send_message(
        message.chat.id,
        "2️⃣ <b>الخطوة الثانية:</b> أرسل <b>اسم القناة</b> باللغة العربية (الذي يظهر على أزرار الاشتراك):\n(مثال: <code>قناة العروض الرسمية</code>)"
    )
    bot.register_next_step_handler(msg, process_adm_add_channel_step2, ch_id)

def process_adm_add_channel_step2(message, ch_id):
    ch_name = message.text.strip()
    msg = bot.send_message(
        message.chat.id,
        "3️⃣ <b>الخطوة الثالثة والأخيرة:</b> أرسل <b>رابط القناة</b>:\n(مثال: <code>https://t.me/mychannel</code>)"
    )
    bot.register_next_step_handler(msg, process_adm_add_channel_step3, ch_id, ch_name)

def process_adm_add_channel_step3(message, ch_id, ch_name):
    ch_url = message.text.strip()
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO channels (channel_id, name, url) VALUES (?, ?, ?)", (ch_id, ch_name, ch_url))
    conn.commit()
    conn.close()
    
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 رجوع لإدارة القنوات", callback_data="adm_channels_menu"))
    
    text = (
        f"✅ <b>تمت إضافة القناة بنجاح!</b>\n\n"
        f"📌 المعرف: <code>{ch_id}</code>\n"
        f"🏷 الاسم: <b>{ch_name}</b>\n"
        f"🔗 الرابط: {ch_url}"
    )
    bot.send_message(message.chat.id, text, reply_markup=kb)

def process_withdraw_amount(message, m_key, min_w, max_w):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        user = get_user(user_id)
        
        if amount < min_w or amount > max_w:
            bot.send_message(user_id, f"❌ <b>المبلغ خارج الحدود المسموحة ({min_w} - {max_w} NPS). تم إلغاء العملية.</b>")
            return

        if user['balance'] < amount:
            bot.send_message(user_id, "❌ <b>رصيدك الحالي غير كافٍ لإجراء هذه العملية.</b>")
            return

        msg = bot.send_message(user_id, "📱 <b>أدخل رقم الحساب / الهاتف المراد تحويل الرصيد عليه:</b>")
        bot.register_next_step_handler(msg, process_withdraw_account, amount, m_key)

    except ValueError:
        bot.send_message(user_id, "❌ <b>القيمة المدخلة غير صالحة. تم إلغاء السحب.</b>")

def process_withdraw_account(message, amount, m_key):
    user_id = message.from_user.id
    acc_num = message.text.strip()
    method_title = "سيريتل كاش" if m_key == "syriatel" else "شام كاش"
    
    # خصم الرصيد مؤقتاً لحين المراجعة
    update_balance(user_id, -amount)
    conn = get_db()
    conn.execute("UPDATE users SET last_withdraw=?, withdrawals_count=withdrawals_count+1 WHERE user_id=?", 
                 (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ <b>تم إرسال طلب السحب بنجاح لقسم المراجعة!</b>")
    
    # إرسال إشعار للمشرف الرئيسي مع أزرار قبول/رفض
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ موافقة وتأكيد", callback_data=f"app_wd_{user_id}_{amount}"),
        types.InlineKeyboardButton("❌ رفض وإعادة الرصيد", callback_data=f"rej_wd_{user_id}_{amount}")
    )
    
    user_info = get_user(user_id)
    admin_msg = (
        f"🚨 <b>طلب سحب رصيد جديد للمراجعة:</b>\n\n"
        f"👤 العميل: {user_info['first_name']} (<code>{user_id}</code>)\n"
        f"💳 الوسيلة: <b>{method_title}</b>\n"
        f"💰 المبلغ المطلوب: <code>{amount}</code> NPS\n"
        f"📱 الحساب/الرقم: <code>{acc_num}</code>\n"
        f"📊 إجمالي سحوباته: {user_info['withdrawals_count']} مرة"
    )
    bot.send_message(SUPER_ADMIN_ID, admin_msg, reply_markup=kb)

def process_promo_code(message):
    user_id = message.from_user.id
    code_text = message.text.strip()
    
    conn = get_db()
    code = conn.execute("SELECT * FROM promo_codes WHERE code=? AND is_active=1", (code_text,)).fetchone()
    
    if not code or code['current_uses'] >= code['max_uses']:
        bot.send_message(user_id, "❌ <b>الكود غير صحيح، أو انتهت صلاحية استخدامه.</b>")
        conn.close()
        return

    reward = code['reward']
    conn.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code=?", (code_text,))
    conn.execute("UPDATE users SET last_promo=? WHERE user_id=?", (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()

    update_balance(user_id, reward)
    bot.send_message(user_id, f"🎉 <b>تم تفعيل الكود بنجاح! حصلت على {reward} NPS!</b>")
    bot.send_message(SUPER_ADMIN_ID, f"🔔 المستخدم <code>{user_id}</code> قام بتفعيل الكود <code>{code_text}</code>")

def process_support_msg(message):
    user_id = message.from_user.id
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💬 الرد على العميل", callback_data=f"reply_supp_{user_id}"))
    
    bot.send_message(SUPER_ADMIN_ID, f"📩 <b>رسالة دعم فني جديدة من</b> <code>{user_id}</code>:\n\n{message.text}", reply_markup=kb)
    bot.send_message(user_id, "✅ <b>تم إرسال رسالتك لفريق الدعم بنجاح.</b>")

def process_reply_support(message, target_uid):
    try:
        bot.send_message(target_uid, f"💬 <b>رد من فريق الدعم الفني:</b>\n\n{message.text}")
        bot.send_message(message.chat.id, "✅ <b>تم إرسال الرد بنجاح.</b>")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ فشل إرسال الرد: {e}")

def process_gen_code(message):
    try:
        parts = message.text.split()
        code, reward, max_uses = parts[0], float(parts[1]), int(parts[2])
        
        conn = get_db()
        conn.execute("INSERT OR REPLACE INTO promo_codes (code, reward, max_uses) VALUES (?, ?, ?)", (code, reward, max_uses))
        conn.commit()
        conn.close()
        
        text = (
            f"✨ <b>تم إنشاء الكود المخصص بنجاح!</b>\n\n"
            f"🎟 الكود: <code>{code}</code>\n"
            f"🎁 المكافأة: <b>{reward} NPS</b>\n"
            f"👥 حد الاستخدام: <b>{max_uses} شخص</b>"
        )
        bot.send_message(message.chat.id, text)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ في تنسيق البيانات: {e}")

def process_adm_user_info(message):
    try:
        uid = int(message.text.strip())
        u = get_user(uid)
        if not u:
            bot.send_message(message.chat.id, "❌ <b>المستخدم غير موجود في قاعدة البيانات.</b>")
            return
        
        text = (
            f"👤 <b>تفاصيل العميل الكاملة (<code>{uid}</code>):</b>\n\n"
            f"👤 الاسم: {u['first_name']}\n"
            f"🏷 المعرف: @{u['username']}\n"
            f"📱 الهاتف: <code>{u['phone']}</code>\n"
            f"💰 الرصيد الحالي: <code>{u['balance']}</code> NPS\n"
            f"👥 عدد الإحالات: <code>{u['referrals_count']}</code>\n"
            f"💳 عمليات السحب: <code>{u['withdrawals_count']}</code>\n"
            f"🔗 المُحيل: <code>{u['referred_by']}</code>"
        )
        bot.send_message(message.chat.id, text)
    except Exception:
        bot.send_message(message.chat.id, "❌ <b>خطأ في إدخال الـ ID.</b>")

def process_adm_add_admin(message):
    try:
        uid = int(message.text.strip())
        conn = get_db()
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ <b>تم إسناد صلاحيات المشرف لـ <code>{uid}</code> بنجاح.</b>")
    except Exception:
        bot.send_message(message.chat.id, "❌ <b>خطأ في إدخال الـ ID.</b>")

def process_adm_private_msg(message):
    try:
        parts = message.text.split(maxsplit=1)
        uid, txt = int(parts[0]), parts[1]
        bot.send_message(uid, f"📩 <b>رسالة خاصة من إدارة البوت:</b>\n\n{txt}")
        bot.send_message(message.chat.id, "✅ <b>تم إرسال الرسالة بنجاح.</b>")
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
            bot.send_message(u['user_id'], f"📢 <b>تنويه عام من الإدارة:</b>\n\n{txt}")
            count += 1
        except Exception:
            pass
    bot.send_message(message.chat.id, f"✅ <b>تم إرسال الإذاعة بنجاح إلى <code>{count}</code> مستخدم.</b>")

def process_adm_ban_user(message):
    try:
        uid = int(message.text.strip())
        u = get_user(uid)
        if not u:
            bot.send_message(message.chat.id, "❌ <b>المستخدم غير موجود.</b>")
            return
        new_ban = 0 if u['is_banned'] else 1
        conn = get_db()
        conn.execute("UPDATE users SET is_banned=? WHERE user_id=?", (new_ban, uid))
        conn.commit()
        conn.close()
        st = "حظر" if new_ban else "إلغاء حظر"
        bot.send_message(message.chat.id, f"✅ <b>تم {st} المستخدم <code>{uid}</code> بنجاح.</b>")
    except Exception:
        bot.send_message(message.chat.id, "❌ <b>خطأ في الـ ID.</b>")

# ==================== خصم الرصيد عند مغادرة القنوات ====================
@bot.chat_member_handler()
def handle_chat_member(update):
    if update.new_chat_member.status in ['left', 'kicked']:
        user_id = update.new_chat_member.user.id
        u = get_user(user_id)
        if u:
            update_balance(user_id, -3)
            try:
                bot.send_message(user_id, "⚠️ <b>تنبيه خصم:</b> تم خصم <b>3 NPS</b> من رصيدك بسبب مغادرتك إحدى القنوات الإجبارية!")
            except Exception:
                pass
            
            ref_id = u['referred_by']
            if ref_id:
                update_balance(ref_id, -3)
                try:
                    bot.send_message(ref_id, f"⚠️ <b>تنبيه خصم:</b> تم خصم <b>3 NPS</b> من رصيدك بسبب مغادرة المستخدم الذي قمت بإحالته (<code>{user_id}</code>) للقناة!")
                except Exception:
                    pass

# ==================== استقبال الرسائل والتفاعل ====================
@bot.message_handler(func=lambda m: True)
def auto_reaction_handler(message):
    send_random_reaction(message.chat.id, message.message_id)

# ==================== تشغيل البوت المباشر ====================
if __name__ == "__main__":
    # إلغاء الـ Webhook القديم لمنع التعارضات
    try:
        bot.remove_webhook()
        print("Webhook successfully removed.")
    except Exception as e:
        print(f"Webhook note: {e}")

    print("⚡️ Aurex Bot Running Successfully...")
    bot.infinity_polling(
        skip_pending=True,
        allowed_updates=['message', 'edited_message', 'callback_query', 'chat_member', 'my_chat_member']
    )

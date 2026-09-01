import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template, request
import sqlite3
import threading
import random
import string
import time
import os

# --- الإعدادات الأساسية ---
TOKEN = "8929555984:AAEVLnYzg6wVmFrpuxICgoLg7t0ttFJcdTg"
MAIN_ADMIN = 8903157513
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- إعداد قاعدة البيانات ---
def init_db():
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, phone TEXT, ichancy_user TEXT, ichancy_pass TEXT, 
                  bot_balance REAL DEFAULT 0, web_balance REAL DEFAULT 0, ref_by INTEGER, 
                  spins INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0, active_refs INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS codes (code TEXT, value REAL, max_uses INTEGER, used INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, role TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, username TEXT, link TEXT)''')
    
    # الإعدادات الافتراضية
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('maintenance', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sham_cash', 'test')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('spacetel_cash', 'test')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('welcome_bonus', '0')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('deposit_bonus_percent', '0')")
    
    # خوارزمية العجلة الافتراضية (نسب مئوية)
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_0', '30')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_5', '20')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_10', '15')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_15', '10')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_25', '10')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_50', '8')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_100', '5')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_500', '1.9')")
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wheel_10000', '0.1')")
    
    # إضافة المطور كأدمن كامل
    c.execute("INSERT OR IGNORE INTO admins (user_id, role) VALUES (?, 'full')", (MAIN_ADMIN,))
    conn.commit()
    return conn

conn = init_db()
c = conn.cursor()

# --- قواميس الذاكرة المؤقتة ---
user_steps = {}
math_captcha = {}

# --- دوال مساعدة ---
def get_setting(key):
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    res = c.fetchone()
    return res[0] if res else None

def is_admin(user_id):
    c.execute("SELECT role FROM admins WHERE user_id=?", (user_id,))
    res = c.fetchone()
    return res[0] if res else False

def check_maintenance(message):
    if get_setting('maintenance') == '1' and not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "البوت حالياً في وضع الصيانة. يرجى العودة لاحقاً 🛠️")
        return True
    return False

def check_subscription(user_id):
    c.execute("SELECT username, link FROM channels")
    channels = c.fetchall()
    for ch in channels:
        try:
            status = bot.get_chat_member(ch[0], user_id).status
            if status in ['left', 'kicked']:
                return False, ch
        except:
            pass
    return True, None

# --- الحماية والبداية ---
@bot.message_handler(commands=['start'])
def start(message):
    if check_maintenance(message): return
    user_id = message.from_user.id
    
    # فحص الحظر
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (user_id,))
    user_data = c.fetchone()
    if user_data and user_data[0] == 1:
        bot.send_message(message.chat.id, "حسابك محظور من استخدام البوت 🚫")
        return

    # الاشتراك الاجباري
    is_subbed, channel = check_subscription(user_id)
    if not is_subbed:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("اشترك الآن", url=channel[1]))
        bot.send_message(message.chat.id, "يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من الاستخدام:", reply_markup=markup)
        return

    # نظام الإحالة
    ref_id = None
    if len(message.text.split()) > 1:
        try:
            ref_id = int(message.text.split()[1])
        except:
            pass

    if not user_data:
        # الكابتشا
        num1, num2 = random.randint(1, 10), random.randint(1, 10)
        math_captcha[user_id] = num1 + num2
        bot.send_message(message.chat.id, f"للتأكد من أنك لست روبوت، كم ناتج: {num1} + {num2} ؟")
        bot.register_next_step_handler(message, verify_captcha, ref_id)
    else:
        main_menu(message)

def verify_captcha(message, ref_id):
    user_id = message.from_user.id
    try:
        if int(message.text) == math_captcha.get(user_id):
            markup = ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(KeyboardButton("مشاركة رقم الهاتف 📱", request_contact=True))
            bot.send_message(message.chat.id, "إجابة صحيحة! يرجى مشاركة رقم هاتفك السوري (+963) للمتابعة.", reply_markup=markup)
            bot.register_next_step_handler(message, verify_phone, ref_id)
        else:
            bot.send_message(message.chat.id, "إجابة خاطئة. اضغط /start للمحاولة مجدداً.")
    except:
        bot.send_message(message.chat.id, "يرجى إدخال أرقام فقط. اضغط /start.")

def verify_phone(message, ref_id):
    if not message.contact:
        bot.send_message(message.chat.id, "يرجى استخدام الزر لمشاركة الرقم. /start")
        return
    phone = message.contact.phone_number
    if not (phone.startswith("963") or phone.startswith("+963")):
        bot.send_message(message.chat.id, "عذراً، البوت متاح للأرقام السورية فقط حصراً 🇸🇾.")
        return
    
    user_id = message.from_user.id
    c.execute("INSERT INTO users (user_id, phone, ref_by) VALUES (?, ?, ?)", (user_id, phone, ref_id))
    conn.commit()
    
    if ref_id:
        bot.send_message(ref_id, f"🎉 قام شخص جديد بالدخول عبر رابط الإحالة الخاص بك!")
        bot.send_message(MAIN_ADMIN, f"👤 دخول جديد للإحالة:\nالمستخدم: {user_id}\nعبر: {ref_id}")
    
    bot.send_message(MAIN_ADMIN, f"👤 مستخدم جديد انضم للبوت:\nالآيدي: {user_id}\nالرقم: {phone}")
    bot.send_message(message.chat.id, "تم التحقق بنجاح! مرحباً بك.", reply_markup=telebot.types.ReplyKeyboardRemove())
    main_menu(message)

# --- القائمة الرئيسية ---
def main_menu(message):
    user_id = message.from_user.id
    c.execute("SELECT ichancy_user FROM users WHERE user_id=?", (user_id,))
    ichancy = c.fetchone()[0]
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if not ichancy:
        markup.add(KeyboardButton("إنشاء حساب ichancy 🆕"))
    else:
        markup.add(KeyboardButton("لوحة العميل 🧑‍💻"))
        markup.add(KeyboardButton("شحن رصيد للبوت 💳"), KeyboardButton("سحب رصيد من البوت 💰"))
        markup.add(KeyboardButton("شحن للموقع 🌐"), KeyboardButton("سحب من الموقع 🏦"))
        markup.add(KeyboardButton("نظام الإحالة 🔗"), KeyboardButton("إدخال كود هدية 🎁"))
        markup.add(KeyboardButton("عجلة الحظ 🎡"), KeyboardButton("إرسال إصابة 🎯"))
        markup.add(KeyboardButton("العروض الحالية 🌟"), KeyboardButton("مراسلة الدعم 🎧"))
    
    if is_admin(user_id):
        markup.add(KeyboardButton("لوحة الإدارة ⚙️"))
        
    bot.send_message(message.chat.id, "اختر من القائمة أدناه:", reply_markup=markup)

# --- إنشاء الحساب ---
@bot.message_handler(func=lambda m: m.text == "إنشاء حساب ichancy 🆕")
def create_ichancy(message):
    user_id = message.from_user.id
    username = "ichancy_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    bonus = float(get_setting('welcome_bonus'))
    
    c.execute("UPDATE users SET ichancy_user=?, ichancy_pass=?, bot_balance=bot_balance+? WHERE user_id=?", 
              (username, password, bonus, user_id))
    
    # إضافة لفة مجانية لجهة الإحالة إن وجدت
    c.execute("SELECT ref_by FROM users WHERE user_id=?", (user_id,))
    ref = c.fetchone()
    if ref and ref[0]:
        c.execute("UPDATE users SET spins=spins+1 WHERE user_id=?", (ref[0],))
        bot.send_message(ref[0], "🎉 حصلت على لفة مجانية في عجلة الحظ لأن أحد إحالاتك أنشأ حساباً!")
        
    conn.commit()
    msg = f"✅ تم إنشاء حسابك بنجاح!\n\nاسم المستخدم: `{username}`\nكلمة المرور: `{password}`\n"
    if bonus > 0:
        msg += f"\n🎁 تم إضافة بونص ترحيبي: {bonus}"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")
    main_menu(message)

# --- الشحن للسحب ---
@bot.message_handler(func=lambda m: m.text in ["شحن رصيد للبوت 💳", "سحب رصيد من البوت 💰"])
def deposit_withdraw_bot(message):
    action = "deposit" if "شحن" in message.text else "withdraw"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("شام كاش", callback_data=f"{action}_sham"),
               InlineKeyboardButton("سيريتل كاش", callback_data=f"{action}_spacetel"))
    bot.send_message(message.chat.id, "اختر طريقة الدفع:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('deposit_') or call.data.startswith('withdraw_'))
def handle_payment_method(call):
    action, method = call.data.split('_')
    user_id = call.from_user.id
    
    if action == "deposit":
        acc = get_setting(f'{method}_cash')
        msg = bot.send_message(call.message.chat.id, f"قم بتحويل المبلغ إلى هذا الرقم:\n`{acc}`\n\nثم أرسل المبلغ الذي قمت بتحويله (أرقام فقط):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_deposit_amount, method)
    else:
        msg = bot.send_message(call.message.chat.id, "أرسل رقم حسابك الذي تريد السحب إليه:")
        bot.register_next_step_handler(msg, process_withdraw_account, method)

def process_deposit_amount(message, method):
    try:
        amount = float(message.text)
        msg = bot.send_message(message.chat.id, "أرسل الآن **رقم العملية** (سيتم قبول أول رقم ترسله فقط):", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_deposit_op, method, amount)
    except:
        bot.send_message(message.chat.id, "مبلغ غير صحيح. أعد المحاولة.")

def process_deposit_op(message, method, amount):
    op_number = message.text.split()[0] # يأخذ أول كلمة/رقم فقط
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("✅ موافقة", callback_data=f"appdep_{message.from_user.id}_{amount}"),
               InlineKeyboardButton("❌ رفض", callback_data=f"rejdep_{message.from_user.id}"))
    
    req_text = f"📥 **طلب شحن جديد**\nالمستخدم: {message.from_user.id}\nالطريقة: {method}\nالمبلغ: {amount}\nرقم العملية: {op_number}"
    bot.send_message(MAIN_ADMIN, req_text, reply_markup=markup, parse_mode="Markdown")
    bot.send_message(message.chat.id, "تم إرسال طلب الشحن للإدارة للمراجعة ⏳.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('appdep_') or call.data.startswith('rejdep_'))
def admin_deposit_action(call):
    if not is_admin(call.from_user.id): return
    data = call.data.split('_')
    action = data[0]
    u_id = int(data[1])
    
    if action == "appdep":
        amount = float(data[2])
        bonus_pct = float(get_setting('deposit_bonus_percent'))
        total = amount + (amount * bonus_pct / 100)
        c.execute("UPDATE users SET bot_balance=bot_balance+? WHERE user_id=?", (total, u_id))
        conn.commit()
        bot.edit_message_text(call.message.text + "\n\n✅ تم الموافقة.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, f"✅ تمت الموافقة على طلب الشحن! تم إضافة {total} إلى رصيدك بالبوت.")
    else:
        bot.edit_message_text(call.message.text + "\n\n❌ تم الرفض.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, "❌ تم رفض طلب الشحن الخاص بك من قبل الإدارة.")

# سحب الرصيد نفس الآلية يتم إرسال الطلب للإدارة
def process_withdraw_account(message, method):
    acc = message.text
    msg = bot.send_message(message.chat.id, "أرسل المبلغ المطلوب سحبه:")
    bot.register_next_step_handler(msg, process_withdraw_amount, method, acc)

def process_withdraw_amount(message, method, acc):
    user_id = message.from_user.id
    try:
        amount = float(message.text)
        c.execute("SELECT bot_balance FROM users WHERE user_id=?", (user_id,))
        bal = c.fetchone()[0]
        if amount > bal:
            bot.send_message(message.chat.id, "رصيدك غير كافٍ.")
            return
            
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("✅ موافقة", callback_data=f"appwit_{user_id}_{amount}"),
                   InlineKeyboardButton("❌ رفض", callback_data=f"rejwit_{user_id}"))
        
        req_text = f"📤 **طلب سحب**\nالمستخدم: {user_id}\nالطريقة: {method}\nالحساب: {acc}\nالمبلغ: {amount}"
        bot.send_message(MAIN_ADMIN, req_text, reply_markup=markup, parse_mode="Markdown")
        
        # خصم مبدئي
        c.execute("UPDATE users SET bot_balance=bot_balance-? WHERE user_id=?", (amount, user_id))
        conn.commit()
        bot.send_message(message.chat.id, "تم إرسال طلب السحب للإدارة ⏳.")
    except:
        bot.send_message(message.chat.id, "مبلغ غير صحيح.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('appwit_') or call.data.startswith('rejwit_'))
def admin_withdraw_action(call):
    if not is_admin(call.from_user.id): return
    data = call.data.split('_')
    action = data[0]
    u_id = int(data[1])
    
    if action == "appwit":
        bot.edit_message_text(call.message.text + "\n\n✅ تم الموافقة.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, "✅ تمت الموافقة على السحب وتحويل المبلغ لحسابك.")
    else:
        amount = float(call.message.text.split("المبلغ: ")[1])
        c.execute("UPDATE users SET bot_balance=bot_balance+? WHERE user_id=?", (amount, u_id)) # إعادة الرصيد
        conn.commit()
        bot.edit_message_text(call.message.text + "\n\n❌ تم الرفض.", call.message.chat.id, call.message.message_id)
        bot.send_message(u_id, "❌ تم رفض طلب السحب وتم إعادة المبلغ لرصيدك.")

# --- لوحة العميل و الإحالات ---
@bot.message_handler(func=lambda m: m.text == "لوحة العميل 🧑‍💻")
def client_panel(message):
    user_id = message.from_user.id
    c.execute("SELECT ichancy_user, ichancy_pass, bot_balance, web_balance FROM users WHERE user_id=?", (user_id,))
    data = c.fetchone()
    text = f"👤 **لوحة حسابك**\n\nاسم الحساب: `{data[0]}`\nكلمة المرور: `{data[1]}`\n\nرصيد البوت: {data[2]}\nرصيد الموقع: {data[3]}"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "نظام الإحالة 🔗")
def ref_system(message):
    user_id = message.from_user.id
    c.execute("SELECT COUNT(*), active_refs FROM users WHERE ref_by=?", (user_id,))
    refs = c.fetchone()
    link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    
    text = (f"🔗 **رابط الإحالة الخاص بك:**\n`{link}`\n\n"
            f"إجمالي الإحالات: {refs[0]}\n"
            f"الإحالات النشطة: {refs[1]}\n\n"
            "ملاحظة: عند وصولك لـ 3 إحالات نشطة تربح 10% من نسبة حرقهم، ولكل شخص ينشئ حساب تحصل على لفة مجانية 🎡.")
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- عجلة الحظ (WebApp) ---
@bot.message_handler(func=lambda m: m.text == "عجلة الحظ 🎡")
def wheel_of_fortune(message):
    user_id = message.from_user.id
    c.execute("SELECT spins FROM users WHERE user_id=?", (user_id,))
    spins = c.fetchone()[0]
    
    if spins <= 0:
        bot.send_message(message.chat.id, "ليس لديك لفات مجانية. قم بدعوة أصدقاء للحصول على لفات! 🎡")
        return
        
    markup = InlineKeyboardMarkup()
    # رابط WebApp سيكون رابط Render الخاص بك
    # مثال: https://your-app-name.onrender.com/wheel?user_id=123
    webapp_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')}/wheel?user_id={user_id}"
    markup.add(InlineKeyboardButton("🎰 افتح العجلة الآن", web_app=WebAppInfo(url=webapp_url)))
    bot.send_message(message.chat.id, f"لديك {spins} لفة مجانية! اضغط الزر أدناه للدوران:", reply_markup=markup)

# --- لوحة الإدارة الشاملة ---
@bot.message_handler(func=lambda m: m.text == "لوحة الإدارة ⚙️")
def admin_panel(message):
    user_id = message.from_user.id
    if not is_admin(user_id): return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("وضع الصيانة", callback_data="admin_maintenance"),
        InlineKeyboardButton("تفاصيل عميل", callback_data="admin_userinfo"),
        InlineKeyboardButton("توليد كود", callback_data="admin_gencode"),
        InlineKeyboardButton("إضافة/خصم رصيد", callback_data="admin_balance"),
        InlineKeyboardButton("رسالة جماعية", callback_data="admin_broadcast"),
        InlineKeyboardButton("إعدادات العجلة", callback_data="admin_wheel"),
        InlineKeyboardButton("إعدادات الشحن", callback_data="admin_deposit_settings")
    )
    bot.send_message(message.chat.id, "🛠️ **لوحة التحكم**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_callbacks(call):
    if not is_admin(call.from_user.id): return
    cmd = call.data.split('_')[1]
    
    if cmd == "maintenance":
        curr = get_setting('maintenance')
        new_val = '0' if curr == '1' else '1'
        c.execute("UPDATE settings SET value=? WHERE key='maintenance'", (new_val,))
        conn.commit()
        status = "مفعل 🔴" if new_val == '1' else "معطل 🟢"
        bot.answer_callback_query(call.id, f"حالة الصيانة الآن: {status}", show_alert=True)
    
    elif cmd == "gencode":
        msg = bot.send_message(call.message.chat.id, "أرسل (القيمة) (عدد الاستخدامات) (عدد الأكواد)\nمثال: 50 10 5")
        bot.register_next_step_handler(msg, admin_generate_codes)
        
    elif cmd == "broadcast":
        msg = bot.send_message(call.message.chat.id, "أرسل الرسالة التي تريد إرسالها للجميع:")
        bot.register_next_step_handler(msg, admin_do_broadcast)

def admin_generate_codes(message):
    try:
        val, max_u, count = map(float, message.text.split())
        codes = []
        for _ in range(int(count)):
            code = "GIFT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            c.execute("INSERT INTO codes (code, value, max_uses) VALUES (?, ?, ?)", (code, val, int(max_u)))
            codes.append(code)
        conn.commit()
        bot.send_message(message.chat.id, "تم توليد الأكواد:\n" + "\n".join(codes))
    except:
        bot.send_message(message.chat.id, "خطأ في الإدخال.")

def admin_do_broadcast(message):
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    count = 0
    for u in users:
        try:
            bot.copy_message(u[0], message.chat.id, message.message_id)
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"تم الإرسال إلى {count} مستخدم.")

# --- خادم Web و WebApp (Flask) ---
@app.route('/')
def home():
    return "Bot is running!"

@app.route('/wheel')
def wheel_page():
    user_id = request.args.get('user_id')
    return render_template('index.html', user_id=user_id)

@app.route('/spin', methods=['POST'])
def spin_api():
    data = request.json
    user_id = data.get('user_id')
    
    c.execute("SELECT spins FROM users WHERE user_id=?", (user_id,))
    res = c.fetchone()
    if not res or res[0] <= 0:
        return {"error": "لا يوجد لفات"}
        
    # جلب النسب
    prizes = [0, 5, 10, 15, 25, 50, 100, 500, 10000]
    weights = []
    for p in prizes:
        weights.append(float(get_setting(f'wheel_{p}')))
        
    won_amount = random.choices(prizes, weights=weights, k=1)[0]
    
    # تحديث الرصيد
    c.execute("UPDATE users SET spins=spins-1, bot_balance=bot_balance+? WHERE user_id=?", (won_amount, user_id))
    conn.commit()
    
    # إشعار الإدارة
    bot.send_message(MAIN_ADMIN, f"🎰 أدار المستخدم {user_id} العجلة وربح {won_amount}")
    bot.send_message(user_id, f"🎉 لقد ربحت {won_amount} من العجلة!")
    
    return {"prize": won_amount}

# --- تشغيل البوت والخادم ---
def run_bot():
    bot.infinity_polling()

if __name__ == '__main__':
    # تشغيل البوت في مسار منفصل (Thread)
    threading.Thread(target=run_bot, daemon=True).start()
    # تشغيل Flask للسيرفر الوهمي و WebApp
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

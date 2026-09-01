import asyncio
import random
import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import aiosqlite

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

from config import BOT_TOKEN, ADMIN_ID, WEB_URL, PORT, DB_NAME
from database import init_db, get_user, get_setting, set_setting, is_admin

logging.basicConfig(level=logging.INFO)

# States
CAPTCHA, PHONE, DEPOSIT_AMOUNT, DEPOSIT_TX, WITHDRAW_ACC, WITHDRAW_AMOUNT, SUPPORT_MSG, GIFT_CODE, HIT_MSG, SITE_TO_BOT, BOT_TO_SITE, ADMIN_STATE = range(12)

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- FASTAPI WEB APP ROUTES ---

@app.get("/wheel", response_class=HTMLResponse)
async def get_wheel(request: Request):
    return templates.TemplateResponse("wheel.html", {"request": request})

@app.get("/api/user_spins")
async def user_spins(user_id: int):
    user = await get_user(user_id)
    return {"spins": user['spins'] if user else 0}

@app.post("/api/spin")
async def process_spin(data: dict):
    user_id = data.get("user_id")
    user = await get_user(user_id)
    if not user or user['spins'] < 1:
        return JSONResponse({"success": False, "message": "لا تملك لفات كافية!"})

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT prize, weight FROM wheel_weights") as cursor:
            weights_data = await cursor.fetchall()

    prizes = [r['prize'] for r in weights_data]
    weights = [r['weight'] for r in weights_data]
    
    won_prize = random.choices(prizes, weights=weights, k=1)[0]

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE users SET spins = spins - 1, bot_balance = bot_balance + ? WHERE telegram_id = ?",
            (won_prize, user_id)
        )
        await db.commit()

    return JSONResponse({"success": True, "prize": won_prize})


# --- TELEGRAM BOT UTILS ---

async def check_sub(bot, user_id):
    ch = await get_setting("channel_username")
    if not ch:
        return True
    try:
        member = await bot.get_chat_member(chat_id=f"@{ch.replace('@','')}", user_id=user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception:
        return True

def get_main_keyboard(is_ichancy_created, user_id, is_admin_user=False):
    ichancy_btn = "👤 حسابي" if is_ichancy_created else "➕ إنشاء حساب iChancy"
    kb = [
        [ichancy_btn, "🎡 عجلة الحظ"],
        ["💳 شحن رصيد للبوت", "🏧 سحب رصيد من البوت"],
        ["📥 شحن إلى الموقع", "📤 سحب من الموقع"],
        ["👥 نظام الإحالة", "🎁 ادخال كود هدية"],
        ["📞 مراسلة الدعم", "🎯 ارسال اصابة"],
        ["🔥 العروض الحالية"]
    ]
    if is_admin_user:
        kb.append(["⚙️ لوحة الإدارة"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

# --- BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check maintenance
    maint = await get_setting("maintenance", "0")
    if maint == "1" and not await is_admin(user_id):
        await update.message.reply_text("⚠️ البوت حالياً في وضع الصيانة. يرجى المحاولة لاحقاً.")
        return ConversationHandler.END

    # Referral parameter
    if context.args and len(context.args) > 0:
        try:
            ref = int(context.args[0])
            if ref != user_id:
                context.user_data['ref_by'] = ref
        except:
            pass

    # Existing user check
    user = await get_user(user_id)
    if user and user['captcha_solved'] and user['phone']:
        # Subscription check
        if not await check_sub(context.bot, user_id):
            ch_link = await get_setting("channel_link", "#")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("اشترك هنا", url=ch_link)],
                [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_sub")]
            ])
            await update.message.reply_text("⚠️ يجب عليك الاشتراك في القناة أولاً لاستخدام البوت:", reply_markup=kb)
            return ConversationHandler.END

        adm = await is_admin(user_id)
        await update.message.reply_text("أهلاً بك في البوت!", reply_markup=get_main_keyboard(user['ichancy_created'], user_id, adm))
        return ConversationHandler.END

    # Anti-Spam Captcha
    num1, num2 = random.randint(1, 10), random.randint(1, 10)
    context.user_data['captcha_ans'] = num1 + num2
    await update.message.reply_text(f"🔒 حماية ضد الرشق والسبام:\nكم حاصل جمع: {num1} + {num2} ؟")
    return CAPTCHA

async def handle_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.message.text
    if ans == str(context.user_data.get('captcha_ans')):
        kb = ReplyKeyboardMarkup([[KeyboardButton("📱 مشاركة رقم الهاتف", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("✅ إجابة صحيحة. يرجى مشاركة رقم هاتفك السوري (+963) للمتابعة:", reply_markup=kb)
        return PHONE
    else:
        await update.message.reply_text("❌ إجابة خاطئة، حاول مجدداً:")
        return CAPTCHA

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    contact = update.message.contact
    if not contact or not contact.phone_number:
        await update.message.reply_text("⚠️ يرجى الضغط على زر مشاركة رقم الهاتف حصراً.")
        return PHONE

    phone = str(contact.phone_number)
    if not (phone.startswith("+963") or phone.startswith("963") or phone.startswith("09")):
        await update.message.reply_text("❌ البوت مخصص للأرقام السورية التي تبدأ بـ +963 فقط.")
        return PHONE

    user_id = update.effective_user.id
    ref_by = context.user_data.get('ref_by')

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, full_name, username, phone, captcha_solved, referred_by)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET phone=excluded.phone, captcha_solved=1
        """, (user_id, update.effective_user.full_name, update.effective_user.username, phone, ref_by))
        await db.commit()

    # Notify Admins and Referrer
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 دخول جديد للبوت:\nالاسم: {update.effective_user.full_name}\nالرقم: {phone}\nالمُحيل: {ref_by or 'لا يوجد'}")
    
    if ref_by:
        try:
            await context.bot.send_message(chat_id=ref_by, text="🎉 انضم شخص جديد للبوت عن طريق رابط الإحالة الخاص بك!")
        except:
            pass

    user = await get_user(user_id)
    adm = await is_admin(user_id)
    await update.message.reply_text("✅ تم التحقق بنجاح!", reply_markup=get_main_keyboard(user['ichancy_created'], user_id, adm))
    return ConversationHandler.END

async def check_sub_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await check_sub(context.bot, user_id):
        await query.answer("✅ تم التحقق من اشتراكك!")
        user = await get_user(user_id)
        adm = await is_admin(user_id)
        await query.message.delete()
        await context.bot.send_message(chat_id=user_id, text="أهلاً بك!", reply_markup=get_main_keyboard(user['ichancy_created'], user_id, adm))
    else:
        await query.answer("❌ لم تشترك في القناة بعد!", show_alert=True)

# --- CLIENT MAIN FEATURES ---

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if not user:
        await update.message.reply_text("يرجى إرسال /start أولاً.")
        return

    # Maintenance Check
    maint = await get_setting("maintenance", "0")
    if maint == "1" and not await is_admin(user_id):
        await update.message.reply_text("⚠️ البوت حالياً في وضع الصيانة.")
        return

    if text == "➕ إنشاء حساب iChancy":
        wb_enabled = await get_setting("welcome_bonus_enabled", "0")
        wb_amount = float(await get_setting("welcome_bonus_amount", "0"))
        
        bonus_msg = ""
        async with aiosqlite.connect(DB_NAME) as db:
            if wb_enabled == "1" and wb_amount > 0:
                await db.execute("UPDATE users SET ichancy_created=1, bot_balance = bot_balance + ? WHERE telegram_id=?", (wb_amount, user_id))
                bonus_msg = f"\n🎁 تم إضافة بونص ترحيبي بقيمة {wb_amount} لرصيدك!"
            else:
                await db.execute("UPDATE users SET ichancy_created=1 WHERE telegram_id=?", (user_id,))
            
            # Give spin to referrer
            if user['referred_by']:
                await db.execute("UPDATE users SET spins = spins + 1 WHERE telegram_id=?", (user['referred_by'],))
                try:
                    await context.bot.send_message(chat_id=user['referred_by'], text="🎉 ربحت لفة مجانية في عجلة الحظ لقيام إحالتك بإنشاء حساب!")
                except:
                    pass
            await db.commit()

        user = await get_user(user_id)
        adm = await is_admin(user_id)
        await update.message.reply_text(
            f"✅ تم إنشاء حساب iChancy بنجاح!\nاسم المستخدم: `{user['ichancy_user']}`\nكلمة المرور: `{user['ichancy_pass']}`{bonus_msg}",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(True, user_id, adm)
        )

    elif text == "👤 حسابي":
        await update.message.reply_text(
            f"👤 **بيانات حسابك:**\n"
            f"🆔 ID: `{user['telegram_id']}`\n"
            f"📱 الرقم: `{user['phone']}`\n"
            f"💰 رصيد البوت: `{user['bot_balance']}`\n"
            f"🌐 رصيد الموقع: `{user['site_balance']}`\n"
            f"🎮 حساب iChancy: `{user['ichancy_user']}`\n"
            f"🔑 كلمة المرور: `{user['ichancy_pass']}`\n"
            f"🎡 لفات العجلة المتبقية: `{user['spins']}`",
            parse_mode="Markdown"
        )

    elif text == "🎡 عجلة الحظ":
        web_url = f"{WEB_URL}/wheel"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("فتح عجلة الحظ 🎡", web_app=WebAppInfo(url=web_url))]])
        await update.message.reply_text("اضغط على الزر أدناه لفتح عجلة الحظ:", reply_markup=kb)

    elif text == "👥 نظام الإحالة":
        async with aiosqlite.connect(DB_NAME) as db:
            # Active refs count (those who deposited)
            async with db.execute("SELECT COUNT(DISTINCT telegram_id) FROM deposits WHERE telegram_id IN (SELECT telegram_id FROM users WHERE referred_by=?) AND status='approved'", (user_id,)) as c:
                active_count = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by=?", (user_id,)) as c:
                total_refs = (await c.fetchone())[0]

        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        burn_status = "🔥 نظام الحرق 10% نشط لديك!" if active_count >= 3 else "⚠️ يلزمك 3 إحالات نشطة لتفعيل 10% نسبة حرق."

        await update.message.reply_text(
            f"👥 **نظام الإحالة المتقدم:**\n\n"
            f"🔗 رابط الإحالة الخاص بك:\n`{ref_link}`\n\n"
            f"📊 إجمالي الإحالات: `{total_refs}`\n"
            f"⚡ الإحالات النشطة (شحنت رصيد): `{active_count}`\n"
            f"🎁 لفات مجانية مكتسبة: لفة واحدة لكل حساب ينشئه صديقك.\n"
            f"💎 {burn_status}\n\n"
            f"*(تراجِع الإدارة نسبة الحرق وتقبضها يدوياً كل 10 أيام)*",
            parse_mode="Markdown"
        )

    elif text == "🔥 العروض الحالية":
        async with aiosqlite.connect(DB_NAME) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM offers") as c:
                offers = await c.fetchall()
        if not offers:
            await update.message.reply_text("لا توجد عروض حالية.")
        else:
            msg = "🔥 **العروض الحالية:**\n\n"
            for o in offers:
                msg += f"📌 **{o['title']}**\n{o['content']}\n------------------\n"
            await update.message.reply_text(msg, parse_mode="Markdown")

# --- CONVERSATION HANDLERS (DEPOSIT / WITHDRAW / PROMO / SUPPORT) ---

# Deposit Flow
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT name, account_info FROM payment_methods WHERE is_active=1") as c:
            methods = await c.fetchall()

    buttons = [[KeyboardButton(m['name'])] for m in methods]
    buttons.append([KeyboardButton("إلغاء")])
    await update.message.reply_text("اختر طريقة الشحن:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True))
    return DEPOSIT_AMOUNT

async def deposit_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = update.message.text
    if method == "إلغاء":
        user = await get_user(update.effective_user.id)
        await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_keyboard(user['ichancy_created'], update.effective_user.id))
        return ConversationHandler.END

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT account_info FROM payment_methods WHERE name=?", (method,)) as c:
            pm = await c.fetchone()

    if not pm:
        await update.message.reply_text("طريقة غير صالحة.")
        return ConversationHandler.END

    context.user_data['dep_method'] = method
    await update.message.reply_text(f"💳 حساب الشحن ({method}):\n`{pm['account_info']}`\n\nالرجاء التحويل ثم أدخل المبلغ المشحون:", parse_mode="Markdown")
    return DEPOSIT_TX

async def deposit_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text)
        context.user_data['dep_amount'] = amt
        await update.message.reply_text("أدخل رقم العملية (سيتم قبول أول رقم يرسل فقط):")
        return DEPOSIT_TX + 1
    except:
        await update.message.reply_text("الرجاء إدخال رقم صحيح للمبلغ:")
        return DEPOSIT_TX

async def deposit_tx_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx = update.message.text
    user_id = update.effective_user.id
    amt = context.user_data['dep_amount']
    method = context.user_data['dep_method']

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("INSERT INTO deposits (telegram_id, method, amount, tx_number) VALUES (?, ?, ?, ?)", (user_id, method, amt, tx))
        dep_id = cursor.lastrowid
        await db.commit()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ موافقة", callback_data=f"dep_app_{dep_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"dep_rej_{dep_id}")]
    ])
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 **طلب شحن جديد # {dep_id}**\nالمستخدم: `{user_id}`\nالطريقة: {method}\nالمبلغ: {amt}\nرقم العملية: `{tx}`",
        parse_mode="Markdown",
        reply_markup=kb
    )

    user = await get_user(user_id)
    await update.message.reply_text("⏳ تم إرسال طلب الشحن إلى الإدارة للمراجعة.", reply_markup=get_main_keyboard(user['ichancy_created'], user_id))
    return ConversationHandler.END

# Admin Deposit Decision Callbacks
async def deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    dep_id = int(data.split("_")[2])

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM deposits WHERE id=?", (dep_id,)) as c:
            dep = await c.fetchone()

        if not dep or dep['status'] != 'pending':
            await query.answer("تم معالجة هذا الطلب مسبقاً.")
            return

        if data.startswith("dep_app"):
            bonus_pct = float(await get_setting("deposit_bonus_percent", "0"))
            final_amount = dep['amount'] + (dep['amount'] * bonus_pct / 100.0)

            await db.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
            await db.execute("UPDATE users SET bot_balance = bot_balance + ? WHERE telegram_id=?", (final_amount, dep['telegram_id']))
            await db.commit()

            await query.edit_message_text(f"{query.message.text}\n\n✅ تم القبول (المبلغ المضاف مع البونص: {final_amount})")
            try:
                await context.bot.send_message(chat_id=dep['telegram_id'], text=f"✅ تم قبول طلب الشحن بقيمة {dep['amount']}! تم إضافة {final_amount} لرصيدك.")
            except:
                pass
        else:
            await db.execute("UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,))
            await db.commit()
            await query.edit_message_text(f"{query.message.text}\n\n❌ تم الرفض")
            try:
                await context.bot.send_message(chat_id=dep['telegram_id'], text="❌ تم رفض طلب الشحن الخاص بك.")
            except:
                pass

# Withdraw Flow
async def start_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT name FROM payment_methods WHERE is_active=1") as c:
            methods = await c.fetchall()

    buttons = [[KeyboardButton(m['name'])] for m in methods]
    buttons.append([KeyboardButton("إلغاء")])
    await update.message.reply_text("اختر طريقة السحب:", reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True))
    return WITHDRAW_ACC

async def withdraw_method_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = update.message.text
    if method == "إلغاء":
        user = await get_user(update.effective_user.id)
        await update.message.reply_text("تم الإلغاء.", reply_markup=get_main_keyboard(user['ichancy_created'], update.effective_user.id))
        return ConversationHandler.END
    context.user_data['with_method'] = method
    await update.message.reply_text("أدخل رقم حسابك الذي ترغب بالسحب إليه:")
    return WITHDRAW_AMOUNT

async def withdraw_acc_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['with_acc'] = update.message.text
    await update.message.reply_text("أدخل المبلغ المطلوب سحبه:")
    return WITHDRAW_AMOUNT + 1

async def withdraw_amount_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text)
        user_id = update.effective_user.id
        user = await get_user(user_id)

        if user['bot_balance'] < amt:
            await update.message.reply_text("❌ رصيدك في البوت غير كافٍ!")
            return ConversationHandler.END

        acc = context.user_data['with_acc']
        method = context.user_data['with_method']

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET bot_balance = bot_balance - ? WHERE telegram_id=?", (amt, user_id))
            cursor = await db.execute("INSERT INTO withdrawals (telegram_id, account_no, amount, method) VALUES (?, ?, ?, ?)", (user_id, acc, amt, method))
            with_id = cursor.lastrowid
            await db.commit()

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ موافقة", callback_data=f"with_app_{with_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"with_rej_{with_id}")]
        ])
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📤 **طلب سحب جديد # {with_id}**\nالمستخدم: `{user_id}`\nالحساب: `{acc}`\nالطريقة: {method}\nالمبلغ: {amt}",
            parse_mode="Markdown",
            reply_markup=kb
        )

        await update.message.reply_text("⏳ تم إرسال طلب السحب للإدارة.", reply_markup=get_main_keyboard(user['ichancy_created'], user_id))
        return ConversationHandler.END
    except:
        await update.message.reply_text("يرجى إدخال مبلغ صحيح.")
        return WITHDRAW_AMOUNT + 1

# Gift Code Redeem
async def redeem_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎁 أدخل كود الهدية:")
    return GIFT_CODE

async def redeem_code_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_text = update.message.text.strip()
    user_id = update.effective_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM promo_codes WHERE code=? AND is_active=1", (code_text,)) as c:
            code = await c.fetchone()

        if not code or code['used_count'] >= code['max_uses']:
            await update.message.reply_text("❌ الكود غير صالح أو انتهت استخداماته.")
            return ConversationHandler.END

        async with db.execute("SELECT * FROM promo_history WHERE telegram_id=? AND code=?", (user_id, code_text)) as c:
            if await c.fetchone():
                await update.message.reply_text("❌ لقد استخدمت هذا الكود مسبقاً!")
                return ConversationHandler.END

        await db.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code=?", (code_text,))
        await db.execute("INSERT INTO promo_history (telegram_id, code) VALUES (?, ?)", (user_id, code_text))
        await db.execute("UPDATE users SET bot_balance = bot_balance + ? WHERE telegram_id=?", (code['value'], user_id))
        await db.commit()

    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🔔 المستخدم `{user_id}` استخدم كود الهدية: `{code_text}` بقيمة {code['value']}")
    user = await get_user(user_id)
    await update.message.reply_text(f"🎉 تم تفعيل الكود بنجاح وإضافة {code['value']} لرصيدك!", reply_markup=get_main_keyboard(user['ichancy_created'], user_id))
    return ConversationHandler.END

# Support & Hit Handlers
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📞 أرسل رسالتك للدعم (يمكنك إرسال نص أو صورة):")
    return SUPPORT_MSG

async def support_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 رد على الرسالة", callback_data=f"reply_sup_{user_id}")]])
    
    if update.message.photo:
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id, caption=f"📩 **رسالة دعم جديدة من:** `{user_id}`\n\n{update.message.caption or ''}", parse_mode="Markdown", reply_markup=kb)
    else:
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📩 **رسالة دعم جديدة من:** `{user_id}`\n\n{update.message.text}", parse_mode="Markdown", reply_markup=kb)

    user = await get_user(user_id)
    await update.message.reply_text("✅ تم إرسال رسالتك للدعم بنجاح.", reply_markup=get_main_keyboard(user['ichancy_created'], user_id))
    return ConversationHandler.END

async def hit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎯 أدخل تفاصيل الإصابة المراد إرسالها:")
    return HIT_MSG

async def hit_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🎯 **إصابة جديدة من:** `{user_id}`\n\n{update.message.text}", parse_mode="Markdown")
    user = await get_user(user_id)
    await update.message.reply_text("✅ تم إرسال تفاصيل الإصابة بنجاح.", reply_markup=get_main_keyboard(user['ichancy_created'], user_id))
    return ConversationHandler.END

# --- ADMIN PANEL ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    role = await is_admin(user_id)
    if not role:
        return

    kb = [
        ["🔧 وضع الصيانة ON/OFF", "🔍 تفاصيل عميل"],
        ["➕ إضافة رصيد", "➖ خصم رصيد"],
        ["🎟️ توليد كود هدية", "📜 الاكواد النشطة"],
        ["📢 رسالة جماعية", "✉️ رسالة خاصة"],
        ["💳 تغيير حسابات الشحن", "🎁 بونص ترحيبي ON/OFF"],
        ["📊 نسبة بونص الشحن", "🎯 نسبة العجلة"],
        ["📢 قناة الاشتراك الإجباري", "👥 قائمة الأدمنية"]
    ]
    await update.message.reply_text("⚙️ **لوحة التحكم بالنظام:**", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

# Cancel Conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    await update.message.reply_text("تم إلغاء العملية.", reply_markup=get_main_keyboard(user['ichancy_created'] if user else 0, update.effective_user.id))
    return ConversationHandler.END

# --- FASTAPI & BOT LIFECYCLE ---

bot_app = Application.builder().token(BOT_TOKEN).build()

def setup_handlers():
    # Converstation for onboarding
    onboard_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CAPTCHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_captcha)],
            PHONE: [MessageHandler(filters.CONTACT, handle_phone)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Deposit conv
    dep_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💳 شحن رصيد للبوت$"), start_deposit)],
        states={
            DEPOSIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_method_chosen)],
            DEPOSIT_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_amount_entered)],
            DEPOSIT_TX + 1: [MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_tx_entered)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Withdraw conv
    with_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🏧 سحب رصيد من البوت$"), start_withdraw)],
        states={
            WITHDRAW_ACC: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_method_chosen)],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_acc_entered)],
            WITHDRAW_AMOUNT + 1: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_entered)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Gift code conv
    gift_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎁 ادخال كود هدية$"), redeem_code_start)],
        states={GIFT_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, redeem_code_process)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Support conv
    sup_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📞 مراسلة الدعم$"), support_start)],
        states={SUPPORT_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, support_process)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Hit conv
    hit_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🎯 ارسال اصابة$"), hit_start)],
        states={HIT_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, hit_process)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    bot_app.add_handler(onboard_handler)
    bot_app.add_handler(dep_handler)
    bot_app.add_handler(with_handler)
    bot_app.add_handler(gift_handler)
    bot_app.add_handler(sup_handler)
    bot_app.add_handler(hit_handler)

    bot_app.add_handler(CallbackQueryHandler(check_sub_cb, pattern="^check_sub$"))
    bot_app.add_handler(CallbackQueryHandler(deposit_callback, pattern="^dep_"))

    bot_app.add_handler(MessageHandler(filters.Regex("^⚙️ لوحة الإدارة$"), admin_panel))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

@app.on_event("startup")
async def startup_event():
    await init_db()
    setup_handlers()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

@app.on_event("shutdown")
async def shutdown_event():
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)

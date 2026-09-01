import aiosqlite
from config import DB_NAME, ADMIN_ID

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Users
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                phone TEXT,
                bot_balance REAL DEFAULT 0.0,
                site_balance REAL DEFAULT 0.0,
                ichancy_created INTEGER DEFAULT 0,
                ichancy_user TEXT DEFAULT 'test',
                ichancy_pass TEXT DEFAULT 'test',
                referred_by INTEGER,
                spins INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                captcha_solved INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Admin Roles: full, support, limited
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY,
                role TEXT DEFAULT 'full'
            )
        """)
        
        # Payment Methods
        await db.execute("""
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                account_info TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Deposits
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deposits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                method TEXT,
                amount REAL,
                tx_number TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Withdrawals
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER,
                account_no TEXT,
                amount REAL,
                method TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Promo Codes
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                value REAL,
                max_uses INTEGER,
                used_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_history (
                telegram_id INTEGER,
                code TEXT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (telegram_id, code)
            )
        """)

        # Offers
        await db.execute("""
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                content TEXT
            )
        """)

        # System Settings
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Wheel Weights (0, 5, 10, 15, 25, 50, 100, 500, 10000)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS wheel_weights (
                prize INTEGER PRIMARY KEY,
                weight REAL DEFAULT 10.0
            )
        """)

        # Default Settings setup
        defaults = [
            ('maintenance', '0'),
            ('channel_username', ''),
            ('channel_link', ''),
            ('welcome_bonus_enabled', '0'),
            ('welcome_bonus_amount', '0'),
            ('deposit_bonus_percent', '0')
        ]
        for key, val in defaults:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

        # Default Payment Methods
        await db.execute("INSERT OR IGNORE INTO payment_methods (name, account_info) VALUES ('شام كاش', 'أدخل رقم شام كاش هنا')")
        await db.execute("INSERT OR IGNORE INTO payment_methods (name, account_info) VALUES ('سيريتل كاش', 'أدخل رقم سيريتل كاش هنا')")

        # Default Admin
        await db.execute("INSERT OR IGNORE INTO admins (telegram_id, role) VALUES (?, 'full')", (ADMIN_ID,))

        # Default Wheel Probabilities
        prizes = [0, 5, 10, 15, 25, 50, 100, 500, 10000]
        for p in prizes:
            w = 50.0 if p == 0 else (10.0 if p <= 25 else 1.0)
            await db.execute("INSERT OR IGNORE INTO wheel_weights (prize, weight) VALUES (?, ?)", (p, w))

        await db.commit()

async def get_user(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cursor:
            return await cursor.fetchone()

async def get_setting(key, default=""):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cursor:
            res = await cursor.fetchone()
            return res[0] if res else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
        await db.commit()

async def is_admin(telegram_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT role FROM admins WHERE telegram_id = ?", (telegram_id,)) as cursor:
            res = await cursor.fetchone()
            return res[0] if res else None

import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH, FREE_DAYS, PREMIUM_DAYS


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            chat_id INTEGER,
            from_user_id INTEGER,
            from_user_name TEXT,
            text TEXT,
            media_type TEXT,
            file_id TEXT,
            date TEXT,
            business_connection_id TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            is_premium INTEGER DEFAULT 0,
            connected_at TEXT,
            referred_by INTEGER DEFAULT NULL,
            premium_until TEXT DEFAULT NULL
        )
    """)

    try:
        c.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE users ADD COLUMN premium_until TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            chat_id INTEGER,
            from_user_name TEXT,
            old_text TEXT,
            new_text TEXT,
            business_connection_id TEXT,
            date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS disappearing (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            chat_id INTEGER,
            from_user_id INTEGER,
            from_user_name TEXT,
            media_type TEXT,
            file_id TEXT,
            business_connection_id TEXT,
            date TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            date TEXT
        )
    """)

    conn.commit()
    conn.close()


# ─── Сообщения ───────────────────────────────────────

def save_message(message, business_connection_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    media_type = None
    file_id = None

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    elif message.document:
        media_type = "document"
        file_id = message.document.file_id
    elif message.voice:
        media_type = "voice"
        file_id = message.voice.file_id
    elif message.sticker:
        media_type = "sticker"
        file_id = message.sticker.file_id
    elif message.video_note:
        media_type = "video_note"
        file_id = message.video_note.file_id

    c.execute("""
        INSERT INTO messages 
        (message_id, chat_id, from_user_id, from_user_name, text, media_type, file_id, date, business_connection_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message.message_id,
        message.chat.id,
        message.from_user.id if message.from_user else None,
        message.from_user.full_name if message.from_user else "Неизвестно",
        message.text or message.caption,
        media_type,
        file_id,
        datetime.now().isoformat(),
        business_connection_id
    ))

    conn.commit()
    conn.close()


def get_message(message_id: int, chat_id: int, business_connection_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT * FROM messages 
        WHERE message_id=? AND chat_id=? AND business_connection_id=?
    """, (message_id, chat_id, business_connection_id))
    row = c.fetchone()
    conn.close()
    return row


# ─── Пользователи ────────────────────────────────────

def save_user(user_id: int, username: str, is_premium: bool = False, referred_by: int = None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    existing = c.fetchone()
    if existing:
        c.execute(
            "UPDATE users SET username=? WHERE user_id=?",
            (username, user_id)
        )
    else:
        c.execute("""
            INSERT INTO users (user_id, username, is_premium, connected_at, referred_by)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, int(is_premium), datetime.now().isoformat(), referred_by))
    conn.commit()
    conn.close()


def is_premium_user(user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_premium, premium_until FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row or not row[0]:
        return False
    
    # Проверяем срок действия (если premium_until = "permanent", то бесконечно)
    if row[1] and row[1] != "permanent":
        premium_until = datetime.fromisoformat(row[1])
        if datetime.now() > premium_until:
            # Подписка истекла
            remove_premium(user_id)
            return False
    
    return True


def set_premium(user_id: int, status: bool, days: int = 30):
    """Выдать или продлить Premium на указанное количество дней (0 = бесконечно)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if status:
        if days == 0:
            # Бесконечная подписка
            premium_until = "permanent"
        else:
            premium_until = (datetime.now() + timedelta(days=days)).isoformat()
        c.execute("UPDATE users SET is_premium=1, premium_until=? WHERE user_id=?", (premium_until, user_id))
    else:
        c.execute("UPDATE users SET is_premium=0, premium_until=NULL WHERE user_id=?", (user_id,))
    
    conn.commit()
    conn.close()


def remove_premium(user_id: int):
    """Отобрать Premium"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_premium=0, premium_until=NULL WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def get_premium_info(user_id: int):
    """Получить информацию о Premium подписке"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_premium, premium_until FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row or not row[0]:
        return None
    
    if row[1] == "permanent":
        return {'active': True, 'until': None, 'days_left': None, 'permanent': True}
    elif row[1]:
        premium_until = datetime.fromisoformat(row[1])
        days_left = (premium_until - datetime.now()).days
        return {'active': True, 'until': premium_until, 'days_left': days_left, 'permanent': False}
    
    return {'active': True, 'until': None, 'days_left': None, 'permanent': False}


def get_all_users() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def check_expired_premiums():
    """Проверить и отключить истекшие подписки"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    now = datetime.now().isoformat()
    c.execute("""
        UPDATE users 
        SET is_premium=0, premium_until=NULL 
        WHERE is_premium=1 AND premium_until < ? AND premium_until != 'permanent'
    """, (now,))
    
    expired_count = c.rowcount
    conn.commit()
    conn.close()
    
    return expired_count


def get_all_users_info():
    """Получить информацию о всех пользователях"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT u.user_id, u.username, u.is_premium, u.connected_at, u.premium_until, u.referred_by
        FROM users u
        ORDER BY u.connected_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def get_username_by_id(user_id: int):
    """Получить имя пользователя по ID"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "Unknown"


# ─── История редактирований ───────────────────────

def save_edit(message_id: int, chat_id: int, from_user_name: str,
              old_text: str, new_text: str, business_connection_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO edits (message_id, chat_id, from_user_name, old_text, new_text, business_connection_id, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (message_id, chat_id, from_user_name, old_text, new_text,
          business_connection_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ─── Исчезающие сообщения ─────────────────────────

def save_disappearing(message, business_connection_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    media_type = None
    file_id = None

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    elif message.video_note:
        media_type = "video_note"
        file_id = message.video_note.file_id
    elif message.voice:
        media_type = "voice"
        file_id = message.voice.file_id
    elif message.document:
        media_type = "document"
        file_id = message.document.file_id
    elif message.sticker:
        media_type = "sticker"
        file_id = message.sticker.file_id

    c.execute("""
        INSERT INTO disappearing 
        (message_id, chat_id, from_user_id, from_user_name, media_type, file_id, business_connection_id, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        message.message_id,
        message.chat.id,
        message.from_user.id if message.from_user else None,
        message.from_user.full_name if message.from_user else "Неизвестно",
        media_type,
        file_id,
        business_connection_id,
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()


# ─── Реферальная система ──────────────────────────

def add_referral(referrer_id: int, referred_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM referrals WHERE referred_id=?", (referred_id,))
    if c.fetchone():
        conn.close()
        return False
    c.execute("""
        INSERT INTO referrals (referrer_id, referred_id, date)
        VALUES (?, ?, ?)
    """, (referrer_id, referred_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return True


def get_referral_count(referrer_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (referrer_id,))
    count = c.fetchone()[0]
    conn.close()
    return count
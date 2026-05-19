import sqlite3
from datetime import datetime, timedelta

DB_NAME = "bot.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT DEFAULT '',
        is_premium INTEGER DEFAULT 0,
        premium_until TEXT DEFAULT '',
        connected_at TEXT DEFAULT '',
        referred_by INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER,
        chat_id INTEGER,
        from_id INTEGER,
        from_name TEXT DEFAULT '',
        text TEXT DEFAULT '',
        media_type TEXT,
        file_id TEXT,
        date TEXT DEFAULT '',
        business_connection_id TEXT DEFAULT '',
        is_deleted INTEGER DEFAULT 0,
        deleted_at TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS edits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER,
        chat_id INTEGER,
        from_name TEXT DEFAULT '',
        old_text TEXT DEFAULT '',
        new_text TEXT DEFAULT '',
        business_connection_id TEXT DEFAULT '',
        edited_at TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_id INTEGER,
        referred_id INTEGER,
        created_at TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS disappearing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER,
        chat_id INTEGER,
        from_id INTEGER,
        from_name TEXT DEFAULT '',
        media_type TEXT,
        file_id TEXT,
        caption TEXT DEFAULT '',
        date TEXT DEFAULT '',
        business_connection_id TEXT DEFAULT ''
    )''')

    # Индексы
    c.execute('''CREATE INDEX IF NOT EXISTS idx_msg_conn
                 ON messages(business_connection_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_msg_chat
                 ON messages(chat_id, business_connection_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_msg_deleted
                 ON messages(is_deleted, business_connection_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_msg_from
                 ON messages(from_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_edits_conn
                 ON edits(business_connection_id)''')

    conn.commit()
    conn.close()


# =============================================
# USERS
# =============================================

def save_user(user_id, username="", is_premium=False, referred_by=0):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))

    if c.fetchone():
        if username:
            c.execute(
                "UPDATE users SET username = ? WHERE user_id = ?",
                (username, user_id)
            )
    else:
        c.execute(
            """INSERT INTO users
               (user_id, username, is_premium, connected_at, referred_by)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, username, int(is_premium),
             datetime.now().isoformat(), referred_by)
        )

    conn.commit()
    conn.close()


def is_premium_user(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT is_premium, premium_until FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return False

    premium_until = row[1]

    if premium_until == "permanent":
        return True

    if premium_until:
        try:
            until = datetime.fromisoformat(premium_until)
            if until < datetime.now():
                # Истёк — сбрасываем
                conn2 = get_db()
                c2 = conn2.cursor()
                c2.execute(
                    "UPDATE users SET is_premium = 0, premium_until = '' WHERE user_id = ?",
                    (user_id,)
                )
                conn2.commit()
                conn2.close()
                return False
            return True
        except Exception:
            pass

    return bool(row[0])


def set_premium(user_id, active, days=30):
    conn = get_db()
    c = conn.cursor()

    if active:
        if days == 0:
            premium_until = "permanent"
        else:
            premium_until = (
                datetime.now() + timedelta(days=days)
            ).isoformat()

        c.execute(
            "UPDATE users SET is_premium = 1, premium_until = ? WHERE user_id = ?",
            (premium_until, user_id)
        )
    else:
        c.execute(
            "UPDATE users SET is_premium = 0, premium_until = '' WHERE user_id = ?",
            (user_id,)
        )

    conn.commit()
    conn.close()


def remove_premium(user_id):
    set_premium(user_id, False)


def get_premium_info(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT is_premium, premium_until FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return {'active': False}

    premium_until = row[1]

    if premium_until == "permanent":
        return {'active': True, 'permanent': True, 'days_left': None}

    if premium_until:
        try:
            until = datetime.fromisoformat(premium_until)
            days_left = (until - datetime.now()).days
            if days_left < 0:
                return {'active': False}
            return {
                'active': True,
                'permanent': False,
                'days_left': days_left
            }
        except Exception:
            pass

    return {'active': bool(row[0])}


def get_username_by_id(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT username FROM users WHERE user_id = ?",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else "Unknown"


def get_all_users_info():
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT user_id, username, is_premium, connected_at,
                  premium_until, referred_by
           FROM users ORDER BY connected_at DESC"""
    )
    rows = c.fetchall()
    conn.close()
    return [tuple(r) for r in rows]


# =============================================
# REFERRALS
# =============================================

def add_referral(referrer_id, referred_id):
    conn = get_db()
    c = conn.cursor()

    # Проверяем что такой реферал уже не существует
    c.execute(
        "SELECT id FROM referrals WHERE referred_id = ?",
        (referred_id,)
    )
    if c.fetchone():
        conn.close()
        return False

    # Проверяем что referrer существует в базе
    c.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (referrer_id,)
    )
    if not c.fetchone():
        conn.close()
        return False

    c.execute(
        """INSERT INTO referrals (referrer_id, referred_id, created_at)
           VALUES (?, ?, ?)""",
        (referrer_id, referred_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return True


def get_referral_count(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?",
        (user_id,)
    )
    count = c.fetchone()[0]
    conn.close()
    return count


# =============================================
# MESSAGES
# =============================================

def save_message(message, business_connection_id):
    conn = get_db()
    c = conn.cursor()

    from_id = message.from_user.id if message.from_user else 0
    from_name = message.from_user.full_name if message.from_user else ""
    text = message.text or message.caption or ""

    media_type = None
    file_id = None

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    elif message.voice:
        media_type = "voice"
        file_id = message.voice.file_id
    elif message.video_note:
        media_type = "video_note"
        file_id = message.video_note.file_id
    elif message.document:
        media_type = "document"
        file_id = message.document.file_id
    elif message.sticker:
        media_type = "sticker"
        file_id = message.sticker.file_id

    # Upsert
    c.execute(
        """SELECT id FROM messages
           WHERE message_id = ? AND chat_id = ? AND business_connection_id = ?""",
        (message.message_id, message.chat.id, business_connection_id)
    )

    if c.fetchone():
        c.execute(
            """UPDATE messages
               SET text = ?, media_type = ?, file_id = ?,
                   from_name = ?, from_id = ?
               WHERE message_id = ? AND chat_id = ? AND business_connection_id = ?""",
            (text, media_type, file_id, from_name, from_id,
             message.message_id, message.chat.id, business_connection_id)
        )
    else:
        c.execute(
            """INSERT INTO messages
               (message_id, chat_id, from_id, from_name, text,
                media_type, file_id, date, business_connection_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (message.message_id, message.chat.id, from_id, from_name,
             text, media_type, file_id,
             datetime.now().isoformat(), business_connection_id)
        )

    # Сохраняем username пользователя
    if message.from_user:
        username = message.from_user.username or ""
        if username or from_id:
            save_user(from_id, username)

    conn.commit()
    conn.close()


def get_message(message_id, chat_id, business_connection_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """SELECT id, message_id, chat_id, from_id, from_name,
                  text, media_type, file_id, date, business_connection_id
           FROM messages
           WHERE message_id = ? AND chat_id = ? AND business_connection_id = ?""",
        (message_id, chat_id, business_connection_id)
    )
    row = c.fetchone()
    conn.close()
    return tuple(row) if row else None


def mark_message_deleted(message_id, chat_id, business_connection_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """UPDATE messages SET is_deleted = 1, deleted_at = ?
           WHERE message_id = ? AND chat_id = ? AND business_connection_id = ?""",
        (datetime.now().isoformat(), message_id, chat_id, business_connection_id)
    )
    conn.commit()
    conn.close()


def save_edit(message_id, chat_id, from_name,
              old_text, new_text, business_connection_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """INSERT INTO edits
           (message_id, chat_id, from_name, old_text, new_text,
            business_connection_id, edited_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (message_id, chat_id, from_name, old_text, new_text,
         business_connection_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def save_disappearing(message, business_connection_id):
    conn = get_db()
    c = conn.cursor()

    from_id = message.from_user.id if message.from_user else 0
    from_name = message.from_user.full_name if message.from_user else ""
    caption = message.caption or ""

    media_type = None
    file_id = None

    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
    elif message.voice:
        media_type = "voice"
        file_id = message.voice.file_id
    elif message.video_note:
        media_type = "video_note"
        file_id = message.video_note.file_id
    elif message.document:
        media_type = "document"
        file_id = message.document.file_id
    elif message.sticker:
        media_type = "sticker"
        file_id = message.sticker.file_id

    c.execute(
        """INSERT OR REPLACE INTO disappearing
           (message_id, chat_id, from_id, from_name, media_type,
            file_id, caption, date, business_connection_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (message.message_id, message.chat.id, from_id, from_name,
         media_type, file_id, caption,
         datetime.now().isoformat(), business_connection_id)
    )
    conn.commit()
    conn.close()


# =============================================
# MINI APP — getData для пользователя
# =============================================

def get_user_connections(user_id):
    """Получить все business_connection_id владельца"""
    conn = get_db()
    c = conn.cursor()

    # Ищем все conn_id где есть сообщения от владельца
    # (владелец сам тоже пишет в бизнес чатах)
    c.execute(
        """SELECT DISTINCT business_connection_id FROM messages
           WHERE from_id = ?""",
        (user_id,)
    )
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_stats_for_user(user_id):
    conn = get_db()
    c = conn.cursor()

    conns = get_user_connections(user_id)

    if not conns:
        conn.close()
        return {'deleted': 0, 'edited': 0, 'total': 0, 'chats': 0}

    placeholders = ','.join('?' * len(conns))

    c.execute(
        f"""SELECT COUNT(*) FROM messages
            WHERE is_deleted = 1
            AND business_connection_id IN ({placeholders})""",
        conns
    )
    deleted = c.fetchone()[0]

    c.execute(
        f"""SELECT COUNT(*) FROM edits
            WHERE business_connection_id IN ({placeholders})""",
        conns
    )
    edited = c.fetchone()[0]

    c.execute(
        f"""SELECT COUNT(*) FROM messages
            WHERE business_connection_id IN ({placeholders})""",
        conns
    )
    total = c.fetchone()[0]

    c.execute(
        f"""SELECT COUNT(DISTINCT chat_id) FROM messages
            WHERE business_connection_id IN ({placeholders})""",
        conns
    )
    chats = c.fetchone()[0]

    conn.close()
    return {
        'deleted': deleted,
        'edited': edited,
        'total': total,
        'chats': chats
    }


def get_deleted_messages_for_user(user_id, page=1, limit=20, chat_id=None):
    conn = get_db()
    c = conn.cursor()
    offset = (page - 1) * limit

    conns = get_user_connections(user_id)
    if not conns:
        conn.close()
        return []

    placeholders = ','.join('?' * len(conns))

    if chat_id:
        params = conns + [int(chat_id), limit, offset]
        c.execute(
            f"""SELECT message_id, chat_id, from_id, from_name,
                       text, media_type, file_id, date, deleted_at
                FROM messages
                WHERE is_deleted = 1
                AND business_connection_id IN ({placeholders})
                AND chat_id = ?
                ORDER BY deleted_at DESC
                LIMIT ? OFFSET ?""",
            params
        )
    else:
        params = conns + [limit, offset]
        c.execute(
            f"""SELECT message_id, chat_id, from_id, from_name,
                       text, media_type, file_id, date, deleted_at
                FROM messages
                WHERE is_deleted = 1
                AND business_connection_id IN ({placeholders})
                ORDER BY deleted_at DESC
                LIMIT ? OFFSET ?""",
            params
        )

    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        # Подтягиваем username если есть
        username = get_username_by_id(r[2]) if r[2] else None
        display = f"@{username}" if (username and username != "Unknown") else r[3]

        result.append({
            'message_id': r[0],
            'chat_id': r[1],
            'from_id': r[2],
            'from_name': display,
            'text': r[4],
            'media_type': r[5],
            'file_id': r[6],
            'date': r[7],
            'deleted_at': r[8]
        })
    return result


def get_edited_messages_for_user(user_id, page=1, limit=20):
    conn = get_db()
    c = conn.cursor()
    offset = (page - 1) * limit

    conns = get_user_connections(user_id)
    if not conns:
        conn.close()
        return []

    placeholders = ','.join('?' * len(conns))
    params = conns + [limit, offset]

    c.execute(
        f"""SELECT message_id, chat_id, from_name, old_text, new_text, edited_at
            FROM edits
            WHERE business_connection_id IN ({placeholders})
            ORDER BY edited_at DESC
            LIMIT ? OFFSET ?""",
        params
    )

    rows = c.fetchall()
    conn.close()

    return [
        {
            'message_id': r[0],
            'chat_id': r[1],
            'from_name': r[2],
            'old_text': r[3],
            'new_text': r[4],
            'edited_at': r[5]
        }
        for r in rows
    ]


def get_chat_list_for_user(user_id):
    conn = get_db()
    c = conn.cursor()

    conns = get_user_connections(user_id)
    if not conns:
        conn.close()
        return []

    placeholders = ','.join('?' * len(conns))
    params = conns + [user_id]

    c.execute(
        f"""SELECT chat_id,
                   MAX(from_name) as name,
                   COUNT(*) as msg_count,
                   SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) as del_count,
                   MAX(date) as last_date
            FROM messages
            WHERE business_connection_id IN ({placeholders})
            AND from_id != ?
            GROUP BY chat_id
            ORDER BY last_date DESC""",
        params
    )

    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        # Пробуем найти лучшее имя для чата
        chat_id = r[0]
        name = r[1] or "Неизвестный"

        result.append({
            'chat_id': chat_id,
            'name': name,
            'message_count': r[2],
            'deleted_count': r[3],
            'last_date': r[4]
        })
    return result


def get_messages_by_chat(user_id, chat_id, page=1, limit=30):
    conn = get_db()
    c = conn.cursor()
    offset = (page - 1) * limit

    conns = get_user_connections(user_id)
    if not conns:
        conn.close()
        return []

    placeholders = ','.join('?' * len(conns))
    params = conns + [int(chat_id), limit, offset]

    c.execute(
        f"""SELECT message_id, chat_id, from_id, from_name,
                   text, media_type, date, is_deleted
            FROM messages
            WHERE business_connection_id IN ({placeholders})
            AND chat_id = ?
            ORDER BY date DESC
            LIMIT ? OFFSET ?""",
        params
    )

    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        username = get_username_by_id(r[2]) if r[2] else None
        display = f"@{username}" if (username and username != "Unknown") else r[3]

        result.append({
            'message_id': r[0],
            'chat_id': r[1],
            'from_id': r[2],
            'from_name': display,
            'text': r[4],
            'media_type': r[5],
            'date': r[6],
            'is_deleted': bool(r[7])
        })
    return result


def search_messages_for_user(user_id, query):
    conn = get_db()
    c = conn.cursor()

    conns = get_user_connections(user_id)
    if not conns:
        conn.close()
        return []

    placeholders = ','.join('?' * len(conns))
    params = conns + [f'%{query}%']

    c.execute(
        f"""SELECT message_id, chat_id, from_id, from_name,
                   text, date, is_deleted, media_type
            FROM messages
            WHERE business_connection_id IN ({placeholders})
            AND text LIKE ?
            ORDER BY date DESC
            LIMIT 50""",
        params
    )

    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        username = get_username_by_id(r[2]) if r[2] else None
        display = f"@{username}" if (username and username != "Unknown") else r[3]

        result.append({
            'message_id': r[0],
            'chat_id': r[1],
            'from_id': r[2],
            'from_name': display,
            'text': r[4],
            'date': r[5],
            'is_deleted': bool(r[6]),
            'media_type': r[7]
        })
    return result


# Запуск при импорте
init_db()

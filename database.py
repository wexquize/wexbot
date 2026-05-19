import os
import asyncio
import asyncpg
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        from urllib.parse import urlparse, unquote

        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        parsed = urlparse(url)

        _pool = await asyncpg.create_pool(
            user=unquote(parsed.username) if parsed.username else None,
            password=unquote(parsed.password) if parsed.password else None,
            host=parsed.hostname,
            port=parsed.port or 5432,
            database=parsed.path.lstrip('/') if parsed.path else 'postgres',
            min_size=1,
            max_size=10,
            command_timeout=30,
            statement_cache_size=0,
            ssl='require',
        )
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT DEFAULT '',
                is_premium INTEGER DEFAULT 0,
                premium_until TEXT DEFAULT '',
                connected_at TEXT DEFAULT '',
                referred_by BIGINT DEFAULT 0
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id BIGSERIAL PRIMARY KEY,
                message_id BIGINT,
                chat_id BIGINT,
                from_id BIGINT,
                from_name TEXT DEFAULT '',
                text TEXT DEFAULT '',
                media_type TEXT,
                file_id TEXT,
                date TEXT DEFAULT '',
                business_connection_id TEXT DEFAULT '',
                is_deleted INTEGER DEFAULT 0,
                deleted_at TEXT DEFAULT ''
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS edits (
                id BIGSERIAL PRIMARY KEY,
                message_id BIGINT,
                chat_id BIGINT,
                from_name TEXT DEFAULT '',
                old_text TEXT DEFAULT '',
                new_text TEXT DEFAULT '',
                business_connection_id TEXT DEFAULT '',
                edited_at TEXT DEFAULT ''
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                id BIGSERIAL PRIMARY KEY,
                referrer_id BIGINT,
                referred_id BIGINT,
                created_at TEXT DEFAULT ''
            )
        ''')

        await conn.execute('''
            CREATE TABLE IF NOT EXISTS disappearing (
                id BIGSERIAL PRIMARY KEY,
                message_id BIGINT,
                chat_id BIGINT,
                from_id BIGINT,
                from_name TEXT DEFAULT '',
                media_type TEXT,
                file_id TEXT,
                caption TEXT DEFAULT '',
                date TEXT DEFAULT '',
                business_connection_id TEXT DEFAULT ''
            )
        ''')

        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_conn ON messages(business_connection_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id, business_connection_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_deleted ON messages(is_deleted, business_connection_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_from ON messages(from_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_msg_unique ON messages(message_id, chat_id, business_connection_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_edits_conn ON edits(business_connection_id)')

        print("✅ Database initialized")


# =============================================
# USERS
# =============================================

async def save_user(user_id, username="", is_premium=False, referred_by=0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT user_id FROM users WHERE user_id = $1",
            user_id
        )
        if existing:
            if username:
                await conn.execute(
                    "UPDATE users SET username = $1 WHERE user_id = $2",
                    username, user_id
                )
        else:
            await conn.execute(
                """INSERT INTO users (user_id, username, is_premium, connected_at, referred_by)
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, username, int(is_premium),
                datetime.now().isoformat(), referred_by
            )


async def is_premium_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_premium, premium_until FROM users WHERE user_id = $1",
            user_id
        )

        if not row or not row['is_premium']:
            return False

        premium_until = row['premium_until']
        if premium_until == "permanent":
            return True

        if premium_until:
            try:
                until = datetime.fromisoformat(premium_until)
                if until < datetime.now():
                    await conn.execute(
                        "UPDATE users SET is_premium = 0, premium_until = '' WHERE user_id = $1",
                        user_id
                    )
                    return False
                return True
            except Exception:
                pass

        return bool(row['is_premium'])


async def set_premium(user_id, active, days=30):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if active:
            if days == 0:
                premium_until = "permanent"
            else:
                premium_until = (datetime.now() + timedelta(days=days)).isoformat()

            await conn.execute(
                "UPDATE users SET is_premium = 1, premium_until = $1 WHERE user_id = $2",
                premium_until, user_id
            )
        else:
            await conn.execute(
                "UPDATE users SET is_premium = 0, premium_until = '' WHERE user_id = $1",
                user_id
            )


async def remove_premium(user_id):
    await set_premium(user_id, False)


async def get_premium_info(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_premium, premium_until FROM users WHERE user_id = $1",
            user_id
        )

        if not row or not row['is_premium']:
            return {'active': False}

        premium_until = row['premium_until']

        if premium_until == "permanent":
            return {'active': True, 'permanent': True, 'days_left': None}

        if premium_until:
            try:
                until = datetime.fromisoformat(premium_until)
                days_left = (until - datetime.now()).days
                if days_left < 0:
                    return {'active': False}
                return {'active': True, 'permanent': False, 'days_left': days_left}
            except Exception:
                pass

        return {'active': bool(row['is_premium'])}


async def get_username_by_id(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username FROM users WHERE user_id = $1",
            user_id
        )
        return row['username'] if row and row['username'] else "Unknown"


async def get_all_users_info():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT user_id, username, is_premium, connected_at,
                      premium_until, referred_by
               FROM users ORDER BY connected_at DESC"""
        )
        return [
            (r['user_id'], r['username'], r['is_premium'], r['connected_at'],
             r['premium_until'], r['referred_by'])
            for r in rows
        ]


# =============================================
# REFERRALS
# =============================================

async def add_referral(referrer_id, referred_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM referrals WHERE referred_id = $1",
            referred_id
        )
        if existing:
            return False

        ref_user = await conn.fetchrow(
            "SELECT user_id FROM users WHERE user_id = $1",
            referrer_id
        )
        if not ref_user:
            return False

        await conn.execute(
            """INSERT INTO referrals (referrer_id, referred_id, created_at)
               VALUES ($1, $2, $3)""",
            referrer_id, referred_id, datetime.now().isoformat()
        )
        return True


async def get_referral_count(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*) as cnt FROM referrals WHERE referrer_id = $1",
            user_id
        )
        return row['cnt'] if row else 0


# =============================================
# MESSAGES
# =============================================

async def save_message(message, business_connection_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
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

        existing = await conn.fetchrow(
            """SELECT id FROM messages
               WHERE message_id = $1 AND chat_id = $2 AND business_connection_id = $3""",
            message.message_id, message.chat.id, business_connection_id
        )

        if existing:
            await conn.execute(
                """UPDATE messages
                   SET text = $1, media_type = $2, file_id = $3,
                       from_name = $4, from_id = $5
                   WHERE message_id = $6 AND chat_id = $7 AND business_connection_id = $8""",
                text, media_type, file_id, from_name, from_id,
                message.message_id, message.chat.id, business_connection_id
            )
        else:
            await conn.execute(
                """INSERT INTO messages
                   (message_id, chat_id, from_id, from_name, text,
                    media_type, file_id, date, business_connection_id)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                message.message_id, message.chat.id, from_id, from_name,
                text, media_type, file_id,
                datetime.now().isoformat(), business_connection_id
            )

        if message.from_user:
            username = message.from_user.username or ""
            if username or from_id:
                await save_user(from_id, username)


async def get_message(message_id, chat_id, business_connection_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """SELECT id, message_id, chat_id, from_id, from_name,
                      text, media_type, file_id, date, business_connection_id
               FROM messages
               WHERE message_id = $1 AND chat_id = $2 AND business_connection_id = $3""",
            message_id, chat_id, business_connection_id
        )
        if not row:
            return None
        return (
            row['id'], row['message_id'], row['chat_id'], row['from_id'],
            row['from_name'], row['text'], row['media_type'], row['file_id'],
            row['date'], row['business_connection_id']
        )


async def mark_message_deleted(message_id, chat_id, business_connection_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE messages SET is_deleted = 1, deleted_at = $1
               WHERE message_id = $2 AND chat_id = $3 AND business_connection_id = $4""",
            datetime.now().isoformat(), message_id, chat_id, business_connection_id
        )


async def save_edit(message_id, chat_id, from_name,
                    old_text, new_text, business_connection_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO edits
               (message_id, chat_id, from_name, old_text, new_text,
                business_connection_id, edited_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            message_id, chat_id, from_name, old_text, new_text,
            business_connection_id, datetime.now().isoformat()
        )


async def save_disappearing(message, business_connection_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
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

        await conn.execute(
            """INSERT INTO disappearing
               (message_id, chat_id, from_id, from_name, media_type,
                file_id, caption, date, business_connection_id)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
            message.message_id, message.chat.id, from_id, from_name,
            media_type, file_id, caption,
            datetime.now().isoformat(), business_connection_id
        )


# =============================================
# MINI APP
# =============================================

async def get_user_connections(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT business_connection_id FROM messages
               WHERE from_id = $1""",
            user_id
        )
        return [r['business_connection_id'] for r in rows]


async def get_stats_for_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conns = await get_user_connections(user_id)

        if not conns:
            return {'deleted': 0, 'edited': 0, 'total': 0, 'chats': 0}

        deleted = await conn.fetchval(
            """SELECT COUNT(*) FROM messages
               WHERE is_deleted = 1 AND business_connection_id = ANY($1::text[])""",
            conns
        )

        edited = await conn.fetchval(
            """SELECT COUNT(*) FROM edits
               WHERE business_connection_id = ANY($1::text[])""",
            conns
        )

        total = await conn.fetchval(
            """SELECT COUNT(*) FROM messages
               WHERE business_connection_id = ANY($1::text[])""",
            conns
        )

        chats = await conn.fetchval(
            """SELECT COUNT(DISTINCT chat_id) FROM messages
               WHERE business_connection_id = ANY($1::text[])""",
            conns
        )

        return {
            'deleted': deleted or 0,
            'edited': edited or 0,
            'total': total or 0,
            'chats': chats or 0
        }


async def get_deleted_messages_for_user(user_id, page=1, limit=20, chat_id=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        offset = (page - 1) * limit
        conns = await get_user_connections(user_id)
        if not conns:
            return []

        if chat_id:
            rows = await conn.fetch(
                """SELECT message_id, chat_id, from_id, from_name,
                          text, media_type, file_id, date, deleted_at
                   FROM messages
                   WHERE is_deleted = 1
                   AND business_connection_id = ANY($1::text[])
                   AND chat_id = $2
                   ORDER BY deleted_at DESC
                   LIMIT $3 OFFSET $4""",
                conns, int(chat_id), limit, offset
            )
        else:
            rows = await conn.fetch(
                """SELECT message_id, chat_id, from_id, from_name,
                          text, media_type, file_id, date, deleted_at
                   FROM messages
                   WHERE is_deleted = 1
                   AND business_connection_id = ANY($1::text[])
                   ORDER BY deleted_at DESC
                   LIMIT $2 OFFSET $3""",
                conns, limit, offset
            )

        result = []
        for r in rows:
            username = await get_username_by_id(r['from_id']) if r['from_id'] else None
            display = f"@{username}" if (username and username != "Unknown") else r['from_name']

            result.append({
                'message_id': r['message_id'],
                'chat_id': r['chat_id'],
                'from_id': r['from_id'],
                'from_name': display,
                'text': r['text'],
                'media_type': r['media_type'],
                'file_id': r['file_id'],
                'date': r['date'],
                'deleted_at': r['deleted_at']
            })
        return result


async def get_edited_messages_for_user(user_id, page=1, limit=20):
    pool = await get_pool()
    async with pool.acquire() as conn:
        offset = (page - 1) * limit
        conns = await get_user_connections(user_id)
        if not conns:
            return []

        rows = await conn.fetch(
            """SELECT message_id, chat_id, from_name, old_text, new_text, edited_at
               FROM edits
               WHERE business_connection_id = ANY($1::text[])
               ORDER BY edited_at DESC
               LIMIT $2 OFFSET $3""",
            conns, limit, offset
        )

        return [
            {
                'message_id': r['message_id'],
                'chat_id': r['chat_id'],
                'from_name': r['from_name'],
                'old_text': r['old_text'],
                'new_text': r['new_text'],
                'edited_at': r['edited_at']
            }
            for r in rows
        ]


async def get_chat_list_for_user(user_id):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conns = await get_user_connections(user_id)
        if not conns:
            return []

        rows = await conn.fetch(
            """SELECT chat_id,
                      MAX(from_name) as name,
                      COUNT(*) as msg_count,
                      SUM(CASE WHEN is_deleted = 1 THEN 1 ELSE 0 END) as del_count,
                      MAX(date) as last_date
               FROM messages
               WHERE business_connection_id = ANY($1::text[])
               AND from_id != $2
               GROUP BY chat_id
               ORDER BY last_date DESC""",
            conns, user_id
        )

        return [
            {
                'chat_id': r['chat_id'],
                'name': r['name'] or "Неизвестный",
                'message_count': r['msg_count'],
                'deleted_count': r['del_count'] or 0,
                'last_date': r['last_date']
            }
            for r in rows
        ]


async def get_messages_by_chat(user_id, chat_id, page=1, limit=30):
    pool = await get_pool()
    async with pool.acquire() as conn:
        offset = (page - 1) * limit
        conns = await get_user_connections(user_id)
        if not conns:
            return []

        rows = await conn.fetch(
            """SELECT message_id, chat_id, from_id, from_name,
                      text, media_type, date, is_deleted
               FROM messages
               WHERE business_connection_id = ANY($1::text[])
               AND chat_id = $2
               ORDER BY date DESC
               LIMIT $3 OFFSET $4""",
            conns, int(chat_id), limit, offset
        )

        result = []
        for r in rows:
            username = await get_username_by_id(r['from_id']) if r['from_id'] else None
            display = f"@{username}" if (username and username != "Unknown") else r['from_name']

            result.append({
                'message_id': r['message_id'],
                'chat_id': r['chat_id'],
                'from_id': r['from_id'],
                'from_name': display,
                'text': r['text'],
                'media_type': r['media_type'],
                'date': r['date'],
                'is_deleted': bool(r['is_deleted'])
            })
        return result


async def search_messages_for_user(user_id, query):
    pool = await get_pool()
    async with pool.acquire() as conn:
        conns = await get_user_connections(user_id)
        if not conns:
            return []

        rows = await conn.fetch(
            """SELECT message_id, chat_id, from_id, from_name,
                      text, date, is_deleted, media_type
               FROM messages
               WHERE business_connection_id = ANY($1::text[])
               AND text ILIKE $2
               ORDER BY date DESC
               LIMIT 50""",
            conns, f'%{query}%'
        )

        result = []
        for r in rows:
            username = await get_username_by_id(r['from_id']) if r['from_id'] else None
            display = f"@{username}" if (username and username != "Unknown") else r['from_name']

            result.append({
                'message_id': r['message_id'],
                'chat_id': r['chat_id'],
                'from_id': r['from_id'],
                'from_name': display,
                'text': r['text'],
                'media_type': r['media_type'],
                'date': r['date'],
                'is_deleted': bool(r['is_deleted'])
            })
        return result

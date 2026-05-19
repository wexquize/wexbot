import hashlib
import hmac
import json
import urllib.parse
import os
import asyncio
import aiohttp
from aiohttp import web

from database import (
    get_deleted_messages_for_user,
    get_edited_messages_for_user,
    get_stats_for_user,
    get_chat_list_for_user,
    get_messages_by_chat,
    search_messages_for_user,
    get_referral_count,
    get_premium_info,
    is_premium_user,
    get_all_users_with_stats,
    set_premium,
    remove_premium,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

GEMINI_API_KEYS = [
    k.strip() for k in os.getenv("GEMINI_API_KEY", "").split(",") if k.strip()
]

_current_key_idx = 0

routes = web.RouteTableDef()


def validate_init_data(init_data):
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calc_hash, received_hash):
            return None

        return json.loads(parsed.get("user", "{}"))
    except Exception as e:
        print(f"Auth err: {e}")
        return None


def get_uid(request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("tma "):
        return None
    user = validate_init_data(auth[4:])
    if not user:
        return None
    try:
        return int(user["id"])
    except Exception:
        return None


def is_admin(request):
    uid = get_uid(request)
    return uid == ADMIN_ID if uid else False


SYSTEM_PROMPT = """Ты — wexquize AI, продвинутый ассистент в Telegram.

ПРАВИЛА:
- Отвечай на русском языке
- Будь полезным, умным и дружелюбным
- Давай развёрнутые ответы когда нужно, краткие — когда уместно
- Используй markdown: **жирный**, *курсив*, `код`, списки
- Помогай с кодом, идеями, объяснениями, советами, переводами
- Если не знаешь — честно скажи
- НЕ упоминай Google, Gemini, что ты модель ИИ
- Ты — wexquize AI, точка"""

def get_next_key():
    global _current_key_idx
    if not GEMINI_API_KEYS:
        return None
    key = GEMINI_API_KEYS[_current_key_idx % len(GEMINI_API_KEYS)]
    _current_key_idx += 1
    return key


# Актуальные модели на 2025
MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]


async def call_gemini(api_key, model, contents):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent?key={api_key}"
    )

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
            "topP": 0.95,
            "topK": 40,
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                return resp.status, await resp.text()
    except asyncio.TimeoutError:
        return 504, "timeout"
    except Exception as e:
        return 0, str(e)


async def ask_gemini(message, history=None):
    if not GEMINI_API_KEYS:
        return "⚠️ AI не настроен"

    print(f"🤖 AI: '{message[:50]}', ключей={len(GEMINI_API_KEYS)}")

    contents = [
        {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]},
        {"role": "model", "parts": [{"text": "Понял! Я wexquize AI, готов помочь с любыми вопросами."}]}
    ]

    if history:
        for msg in history[-10:]:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("text", "")}]})

    contents.append({"role": "user", "parts": [{"text": message}]})

    errors = []
    for ki in range(len(GEMINI_API_KEYS)):
        api_key = get_next_key()
        if not api_key:
            continue

        for model in MODELS:
            status, text = await call_gemini(api_key, model, contents)
            print(f"🔍 {model} key#{ki}: status={status}")

            if status == 200:
                try:
                    data = json.loads(text)
                    candidates = data.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        continue
                    answer = parts[0].get("text", "").strip()
                    if answer:
                        print(f"✅ AI: {model}")
                        return answer
                except Exception:
                    continue

            elif status == 429:
                errors.append(f"{model}:limit")
                continue
            elif status == 404:
                continue
            else:
                errors.append(f"{model}:{status}")

    return "⚠️ AI временно недоступен. Подожди минуту."

@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok", "ai_keys": len(GEMINI_API_KEYS)})


@routes.get("/api/stats")
async def api_stats(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        stats = await get_stats_for_user(uid)
        premium = await get_premium_info(uid)
        refs = await get_referral_count(uid)
        return web.json_response({
            "deleted_count": stats.get("deleted", 0),
            "edited_count": stats.get("edited", 0),
            "total_saved": stats.get("total", 0),
            "chats_count": stats.get("chats", 0),
            "premium": premium or {"active": False},
            "referrals": refs,
            "is_admin": uid == ADMIN_ID
        })
    except Exception as e:
        print(f"Stats err: {e}")
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/chats")
async def api_chats(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        chats = await get_chat_list_for_user(uid)
        return web.json_response({"chats": chats})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/deleted")
async def api_deleted(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        page = int(request.query.get("page", 1))
        limit = int(request.query.get("limit", 20))
        chat_id = request.query.get("chat_id")
        msgs = await get_deleted_messages_for_user(uid, page, limit, chat_id)
        return web.json_response({"messages": msgs, "page": page})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/edited")
async def api_edited(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        page = int(request.query.get("page", 1))
        limit = int(request.query.get("limit", 20))
        msgs = await get_edited_messages_for_user(uid, page, limit)
        return web.json_response({"messages": msgs, "page": page})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/chat/{chat_id}")
async def api_chat(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        chat_id = request.match_info["chat_id"]
        page = int(request.query.get("page", 1))
        msgs = await get_messages_by_chat(uid, chat_id, page, 30)
        return web.json_response({"messages": msgs, "page": page})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/api/search")
async def api_search(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        q = (request.query.get("q") or "").strip()
        if len(q) < 2:
            return web.json_response({"results": []})
        results = await search_messages_for_user(uid, q)
        return web.json_response({"results": results})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


@routes.post("/api/ai")
async def api_ai(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Bad request"}, status=400)

    message = (body.get("message") or "").strip()
    if not message:
        return web.json_response({"error": "Empty"}, status=400)
    if len(message) > 2000:
        return web.json_response({"error": "Too long"}, status=400)

    history = body.get("history", [])
    answer = await ask_gemini(message, history)
    return web.json_response({"reply": answer})


@routes.get("/api/admin/users")
async def admin_users(request):
    if not is_admin(request):
        return web.json_response({"error": "Forbidden"}, status=403)
    try:
        users = await get_all_users_with_stats()
        return web.json_response({"users": users})
    except Exception as e:
        print(f"Admin users err: {e}")
        return web.json_response({"error": str(e)}, status=500)


@routes.post("/api/admin/premium")
async def admin_premium(request):
    if not is_admin(request):
        return web.json_response({"error": "Forbidden"}, status=403)
    try:
        body = await request.json()
        uid = int(body.get("user_id", 0))
        action = body.get("action", "give")
        days = int(body.get("days", 30))

        if not uid:
            return web.json_response({"error": "No user_id"}, status=400)

        if action == "give":
            await set_premium(uid, True, days=days)

            # Уведомляем пользователя через бота
            try:
                from aiogram import Bot
                bot = Bot(token=BOT_TOKEN)

                if days == 0:
                    text = (
                        "⭐ <b>Тебе выдан БЕСКОНЕЧНЫЙ Premium!</b> ♾️\n\n"
                        "Теперь доступны:\n"
                        "📸 Удалённые фото\n"
                        "🎥 Удалённые видео\n"
                        "🎤 Удалённые голосовые\n"
                        "📁 Удалённые файлы\n"
                        "🎭 Удалённые стикеры\n"
                        "📹 Удалённые кружки"
                    )
                else:
                    text = (
                        f"⭐ <b>Тебе выдан Premium на {days} дней!</b>\n\n"
                        "Теперь доступны:\n"
                        "📸 Удалённые фото\n"
                        "🎥 Удалённые видео\n"
                        "🎤 Удалённые голосовые\n"
                        "📁 Удалённые файлы\n"
                        "🎭 Удалённые стикеры\n"
                        "📹 Удалённые кружки"
                    )

                await bot.send_message(uid, text, parse_mode="HTML")
                await bot.session.close()
            except Exception as e:
                print(f"Notify err: {e}")

            return web.json_response({"ok": True, "action": "given", "days": days})

        elif action == "remove":
            await remove_premium(uid)

            try:
                from aiogram import Bot
                bot = Bot(token=BOT_TOKEN)
                await bot.send_message(
                    uid,
                    "❌ <b>Ваша Premium подписка отключена</b>\n\n"
                    "Если считаете что произошла ошибка — напишите @wexquize",
                    parse_mode="HTML"
                )
                await bot.session.close()
            except Exception as e:
                print(f"Notify err: {e}")

            return web.json_response({"ok": True, "action": "removed"})
        else:
            return web.json_response({"error": "Unknown action"}, status=400)
    except Exception as e:
        print(f"Admin premium err: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def create_app():
    app = web.Application()
    try:
        import aiohttp_cors
        cors = aiohttp_cors.setup(app, defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "OPTIONS"]
            )
        })
        app.router.add_routes(routes)
        for r in list(app.router.routes()):
            try:
                cors.add(r)
            except Exception:
                pass
    except ImportError:
        app.router.add_routes(routes)
    return app

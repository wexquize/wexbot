import hashlib
import hmac
import json
import urllib.parse
import os
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
    is_premium_user
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

routes = web.RouteTableDef()


# =========================
# AUTH
# =========================
def validate_init_data(init_data: str) -> dict | None:
    try:
        parsed = dict(
            urllib.parse.parse_qsl(init_data, keep_blank_values=True)
        )
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calc_hash = hmac.new(
            secret,
            data_check.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calc_hash, received_hash):
            return None

        return json.loads(parsed.get("user", "{}"))
    except Exception as e:
        print(f"Auth err: {e}")
        return None


def get_uid(request) -> int | None:
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


# =========================
# AI — Gemini
# =========================
GEMINI_URL = (
    "https://generativelanguage.googleapis.com"
    "/v1beta/models/gemini-2.0-flash:generateContent"
)

SYSTEM_PROMPT = """Ты — умный ассистент внутри приложения wexquize mode.
Приложение сохраняет удалённые и отредактированные сообщения в Telegram.
Отвечай коротко, по делу, на русском языке.
Ты можешь помочь с любыми вопросами пользователя.
Не упоминай что ты Gemini или Google — ты wexquize AI."""


async def ask_gemini(message: str, history: list = None) -> str:
    if not GEMINI_API_KEY:
        return "⚠️ AI временно недоступен"

    contents = []

    # Системный промпт
    contents.append({
        "role": "user",
        "parts": [{"text": f"[SYSTEM]: {SYSTEM_PROMPT}"}]
    })
    contents.append({
        "role": "model",
        "parts": [{"text": "Понял, я wexquize AI. Готов помочь!"}]
    })

    # История диалога
    if history:
        for msg in history[-10:]:  # Последние 10 сообщений
            role = "user" if msg["role"] == "user" else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["text"]}]
            })

    # Текущее сообщение
    contents.append({
        "role": "user",
        "parts": [{"text": message}]
    })

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024,
            "topP": 0.95,
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    print(f"Gemini {resp.status}: {err[:200]}")
                    return "⚠️ AI временно недоступен, попробуй позже"

                data = await resp.json()
                candidates = data.get("candidates", [])
                if not candidates:
                    return "🤔 Не удалось получить ответ"

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    return "🤔 Пустой ответ"

                return parts[0].get("text", "🤔 Нет текста")

    except asyncio.TimeoutError:
        return "⏳ AI думает слишком долго, попробуй позже"
    except Exception as e:
        print(f"Gemini error: {e}")
        return "⚠️ Ошибка AI"


# =========================
# ROUTES
# =========================
@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok"})


@routes.get("/api/stats")
async def api_stats(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    stats = get_stats_for_user(uid)
    premium = get_premium_info(uid)
    refs = get_referral_count(uid)

    return web.json_response({
        "deleted_count": stats.get("deleted", 0),
        "edited_count": stats.get("edited", 0),
        "total_saved": stats.get("total", 0),
        "chats_count": stats.get("chats", 0),
        "premium": premium or {"active": False},
        "referrals": refs
    })


@routes.get("/api/chats")
async def api_chats(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    chats = get_chat_list_for_user(uid)
    return web.json_response({"chats": chats})


@routes.get("/api/deleted")
async def api_deleted(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    page = int(request.query.get("page", 1))
    limit = int(request.query.get("limit", 20))
    chat_id = request.query.get("chat_id")

    msgs = get_deleted_messages_for_user(uid, page, limit, chat_id)
    return web.json_response({"messages": msgs, "page": page})


@routes.get("/api/edited")
async def api_edited(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    page = int(request.query.get("page", 1))
    limit = int(request.query.get("limit", 20))

    msgs = get_edited_messages_for_user(uid, page, limit)
    return web.json_response({"messages": msgs, "page": page})


@routes.get("/api/chat/{chat_id}")
async def api_chat(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    chat_id = request.match_info["chat_id"]
    page = int(request.query.get("page", 1))

    msgs = get_messages_by_chat(uid, chat_id, page, 30)
    return web.json_response({"messages": msgs, "page": page})


@routes.get("/api/search")
async def api_search(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    q = (request.query.get("q") or "").strip()
    if len(q) < 2:
        return web.json_response({"results": []})

    results = search_messages_for_user(uid, q)
    return web.json_response({"results": results})


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
        return web.json_response({"error": "Empty message"}, status=400)

    if len(message) > 2000:
        return web.json_response(
            {"error": "Message too long"}, status=400
        )

    history = body.get("history", [])

    answer = await ask_gemini(message, history)

    return web.json_response({"reply": answer})


@routes.get("/api/export")
async def api_export(request):
    uid = get_uid(request)
    if not uid:
        return web.json_response({"error": "Unauthorized"}, status=401)

    if not is_premium_user(uid):
        return web.json_response(
            {"error": "Premium required"}, status=403
        )

    msgs = get_deleted_messages_for_user(uid, 1, 500)

    lines = ["=== wexquize mode export ===", ""]
    for m in msgs:
        dt = m.get("deleted_at") or m.get("date", "")
        name = m.get("from_name", "?")
        txt = m.get("text") or f"[{m.get('media_type', 'media')}]"
        lines.append(f"[{dt}] {name}: {txt}")

    return web.Response(
        text="\n".join(lines),
        content_type="text/plain",
        headers={
            "Content-Disposition":
                'attachment; filename="deleted.txt"'
        }
    )


# =========================
# APP FACTORY
# =========================
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

import hashlib
import hmac
import json
import urllib.parse
import os
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

routes = web.RouteTableDef()


# =========================
# Telegram Mini App auth
# =========================
def validate_telegram_init_data(init_data: str) -> dict | None:
    """
    Проверка initData от Telegram WebApp.
    Authorization header приходит как: "tma <initData>"
    """
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        user_json = parsed.get("user", "{}")
        return json.loads(user_json)

    except Exception as e:
        print("validate_telegram_init_data error:", e)
        return None


def get_user_id_from_request(request: web.Request) -> int | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("tma "):
        return None

    init_data = auth[4:]
    user = validate_telegram_init_data(init_data)
    if not user:
        return None

    try:
        return int(user.get("id"))
    except Exception:
        return None


# =========================
# Routes
# =========================
@routes.get("/health")
async def health(request):
    return web.json_response({"status": "ok"})


@routes.get("/api/stats")
async def api_stats(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    stats = get_stats_for_user(user_id)
    premium = get_premium_info(user_id)
    referrals = get_referral_count(user_id)

    return web.json_response({
        "deleted_count": stats.get("deleted", 0),
        "edited_count": stats.get("edited", 0),
        "total_saved": stats.get("total", 0),
        "chats_count": stats.get("chats", 0),
        "premium": premium if premium else {"active": False},
        "referrals": referrals
    })


@routes.get("/api/chats")
async def api_chats(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    chats = get_chat_list_for_user(user_id)
    return web.json_response({"chats": chats})


@routes.get("/api/deleted")
async def api_deleted(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    page = int(request.query.get("page", 1))
    limit = int(request.query.get("limit", 20))
    chat_id = request.query.get("chat_id")

    messages = get_deleted_messages_for_user(
        user_id=user_id,
        page=page,
        limit=limit,
        chat_id=chat_id
    )
    return web.json_response({"messages": messages, "page": page})


@routes.get("/api/edited")
async def api_edited(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    page = int(request.query.get("page", 1))
    limit = int(request.query.get("limit", 20))

    messages = get_edited_messages_for_user(user_id, page=page, limit=limit)
    return web.json_response({"messages": messages, "page": page})


@routes.get("/api/chat/{chat_id}")
async def api_chat(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    chat_id = request.match_info["chat_id"]
    page = int(request.query.get("page", 1))

    messages = get_messages_by_chat(user_id, chat_id, page=page, limit=30)
    return web.json_response({"messages": messages, "page": page})


@routes.get("/api/search")
async def api_search(request):
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    q = (request.query.get("q") or "").strip()
    if len(q) < 2:
        return web.json_response({"results": []})

    results = search_messages_for_user(user_id, q)
    return web.json_response({"results": results})


@routes.get("/api/export_deleted_txt")
async def api_export_deleted_txt(request):
    """
    Экспорт удалённых сообщений в txt (Premium).
    """
    user_id = get_user_id_from_request(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    if not is_premium_user(user_id):
        return web.json_response({"error": "Premium required"}, status=403)

    messages = get_deleted_messages_for_user(user_id, page=1, limit=500)

    lines = ["=== wexquize mode — deleted messages export ===", ""]
    for m in messages:
        lines.append(f"[{m.get('deleted_at') or m.get('date')}] {m.get('from_name')}:")
        if m.get("text"):
            lines.append(m["text"])
        elif m.get("media_type"):
            lines.append(f"[media: {m['media_type']}]")
        else:
            lines.append("(empty)")
        lines.append("")

    content = "\n".join(lines)

    return web.Response(
        text=content,
        content_type="text/plain",
        headers={
            "Content-Disposition": 'attachment; filename="deleted_messages.txt"'
        }
    )


async def create_app():
    app = web.Application()

    # CORS (чтобы GitHub Pages мог дергать API)
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
    except Exception:
        app.router.add_routes(routes)

    return app

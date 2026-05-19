from aiogram import Router
from aiogram.types import (
    Message, BusinessConnection, BusinessMessagesDeleted,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.filters import CommandStart, Command
from database import (
    save_message,
    get_message,
    save_user,
    is_premium_user,
    set_premium,
    remove_premium,
    get_premium_info,
    save_disappearing,
    save_edit,
    add_referral,
    get_referral_count,
    get_all_users_info,
    get_username_by_id,
    mark_message_deleted
)
from config import ADMIN_ID, REFERRALS_FOR_PREMIUM, MINIAPP_URL

router = Router()


def app_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="📱 Открыть wexquize mode",
            web_app=WebAppInfo(url=MINIAPP_URL)
        )
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id

    if message.text and message.text.startswith("/start ref_"):
        try:
            ref_id = int(message.text.split("ref_")[1])
            if ref_id != user_id:
                added = await add_referral(ref_id, user_id)
                if added:
                    rc = await get_referral_count(ref_id)
                    try:
                        await message.bot.send_message(
                            ref_id,
                            f"🎉 Новый реферал!\n👤 {message.from_user.full_name}\n📊 {rc}/{REFERRALS_FOR_PREMIUM}"
                        )
                    except Exception:
                        pass

                    if rc >= REFERRALS_FOR_PREMIUM:
                        ip = await is_premium_user(ref_id)
                        if not ip:
                            await set_premium(ref_id, True, days=30)
                            try:
                                await message.bot.send_message(ref_id, "⭐ Premium на 30 дней!")
                            except Exception:
                                pass

                    await save_user(user_id, message.from_user.username or "", referred_by=ref_id)
        except Exception as e:
            print(f"Ref err: {e}")

    await save_user(user_id, message.from_user.username or "")

    await message.answer(
        "👁 <b>wexquize mode</b>\n\n"
        "Бот сохраняет удалённые сообщения.\n\n"
        "📱 Настройки → Telegram Business → Чат-боты\n\n"
        "Всё в приложении 👇",
        parse_mode="HTML",
        reply_markup=app_keyboard()
    )


@router.message(Command("app"))
async def cmd_app(message: Message):
    await message.answer("👁 wexquize mode", reply_markup=app_keyboard())


@router.message(Command("ref"))
async def cmd_ref(message: Message):
    uid = message.from_user.id
    rc = await get_referral_count(uid)
    me = await message.bot.me()
    link = f"https://t.me/{me.username}?start=ref_{uid}"
    await message.answer(
        f"🎁 Реферальная программа\n\n👥 {rc}/{REFERRALS_FOR_PREMIUM}\n\n🔗 <code>{link}</code>",
        parse_mode="HTML"
    )


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Всё в приложении 👇", reply_markup=app_keyboard())
        return

    args = message.text.split()
    if len(args) >= 2 and args[1] != "remove":
        try:
            uid = int(args[1])
            days = int(args[2]) if len(args) >= 3 else 30
            await set_premium(uid, True, days=days)
            lbl = "♾️" if days == 0 else f"{days}д"
            await message.answer(f"✅ Premium {lbl} → {uid}")
            try:
                await message.bot.send_message(uid, "⭐ Тебе выдан Premium!")
            except Exception:
                pass
        except ValueError:
            await message.answer("❌ /premium UID [DAYS]")

    elif len(args) == 3 and args[1] == "remove":
        try:
            uid = int(args[2])
            await remove_premium(uid)
            await message.answer(f"✅ Premium убран у {uid}")
        except ValueError:
            await message.answer("❌ /premium remove UID")
    else:
        await message.answer("/premium UID [DAYS]\n/premium remove UID\n/users")


@router.message(Command("users"))
async def cmd_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    users = await get_all_users_info()
    if not users:
        await message.answer("Нет пользователей")
        return

    total = len(users)
    prem = sum(1 for u in users if u[2])
    text = f"👥 {total} (⭐{prem})\n\n"

    for uid, uname, is_prem, cat, put, rb in users:
        name = f"@{uname}" if uname else f"ID{uid}"
        s = "⭐" if is_prem else "🆓"
        try:
            d = __import__('datetime').datetime.fromisoformat(cat).strftime("%d.%m")
        except Exception:
            d = "?"
        line = f"{s} {name} · <code>{uid}</code> · {d}\n"
        if len(text + line) > 4000:
            await message.answer(text, parse_mode="HTML")
            text = line
        else:
            text += line

    if text:
        await message.answer(text, parse_mode="HTML")


@router.business_connection()
async def on_bc(event: BusinessConnection):
    await save_user(event.user.id, event.user.username or "")
    try:
        if event.is_enabled:
            await event.bot.send_message(
                event.user.id,
                "✅ wexquize mode подключён!\nСообщения сохраняются 🚀",
                reply_markup=app_keyboard()
            )
    except Exception as e:
        print(f"Conn err: {e}")


@router.business_message()
async def on_bm(message: Message):
    try:
        if not message.business_connection_id:
            return
        await save_message(message, message.business_connection_id)
        if (message.photo or message.video or message.voice or
            message.video_note or message.document or message.sticker):
            await save_disappearing(message, message.business_connection_id)
    except Exception as e:
        print(f"Save err: {e}")


@router.edited_business_message()
async def on_be(message: Message):
    try:
        if not message.business_connection_id:
            return

        old = await get_message(
            message.message_id,
            message.chat.id,
            message.business_connection_id
        )
        if not old:
            return

        ot = old[5]
        nt = message.text or message.caption
        if ot == nt:
            return

        fn = message.from_user.full_name if message.from_user else ""
        fu = message.from_user.username if message.from_user else None

        if fu:
            disp = f"@{fu}"
        elif message.from_user:
            disp = f"<a href='tg://user?id={message.from_user.id}'>{fn}</a>"
        else:
            disp = fn

        await save_edit(
            message.message_id, message.chat.id, fn,
            ot or "", nt or "", message.business_connection_id
        )

        bc = await message.bot.get_business_connection(message.business_connection_id)
        oid = bc.user.id

        await message.bot.send_message(
            oid,
            f"✏️ Редактирование\n👤 {disp}\n\n<b>Было:</b>\n<blockquote>{ot or '(пусто)'}</blockquote>\n\n<b>Стало:</b>\n<blockquote>{nt or '(пусто)'}</blockquote>",
            parse_mode="HTML"
        )

        await save_message(message, message.business_connection_id)
    except Exception as e:
        print(f"Edit err: {e}")


@router.deleted_business_messages()
async def on_bmd(event: BusinessMessagesDeleted):
    try:
        cid = event.business_connection_id
        bc = await event.bot.get_business_connection(cid)
        oid = bc.user.id

        for mid in event.message_ids:
            try:
                row = await get_message(mid, event.chat.id, cid)
                if not row:
                    continue

                (_, _, cid_, fid, fname, text, mtype, fid_, date, _) = row
                await mark_message_deleted(mid, event.chat.id, cid)

                if fid == oid:
                    continue

                un = await get_username_by_id(fid) if fid else None
                if un and un != "Unknown":
                    disp = f"@{un}"
                elif fid:
                    disp = f"<a href='tg://user?id={fid}'>{fname}</a>"
                else:
                    disp = fname

                prem = await is_premium_user(oid)
                ts = date[:16].replace('T', ' ') if date else ""

                hdr = f"🗑️ <b>Удалено</b>\n👤 {disp}\n🕐 {ts}"

                if mtype is None:
                    await event.bot.send_message(oid, hdr + f"\n\n<blockquote>{text or '(пусто)'}</blockquote>", parse_mode="HTML")
                elif prem:
                    try:
                        if mtype == "photo":
                            await event.bot.send_photo(oid, fid_, caption=hdr, parse_mode="HTML")
                        elif mtype == "video":
                            await event.bot.send_video(oid, fid_, caption=hdr, parse_mode="HTML")
                        elif mtype == "voice":
                            await event.bot.send_voice(oid, fid_, caption=hdr, parse_mode="HTML")
                        elif mtype == "document":
                            await event.bot.send_document(oid, fid_, caption=hdr, parse_mode="HTML")
                        elif mtype == "sticker":
                            await event.bot.send_message(oid, hdr, parse_mode="HTML")
                            await event.bot.send_sticker(oid, fid_)
                        elif mtype == "video_note":
                            await event.bot.send_message(oid, hdr, parse_mode="HTML")
                            await event.bot.send_video_note(oid, fid_)
                    except Exception:
                        await event.bot.send_message(oid, hdr + f"\n\n📎 {mtype}", parse_mode="HTML")
                else:
                    em = {"photo": "📸", "video": "🎥", "voice": "🎤", "document": "📁", "sticker": "🎭", "video_note": "📹"}
                    e = em.get(mtype, "📎")
                    await event.bot.send_message(oid, hdr + f"\n\n{e} Медиа · Откройте приложение", parse_mode="HTML", reply_markup=app_keyboard())

            except Exception as e:
                print(f"Del {mid} err: {e}")
    except Exception as e:
        print(f"Deleted err: {e}")

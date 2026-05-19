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
from datetime import datetime

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

    # Реферальная система
    if message.text and message.text.startswith("/start ref_"):
        try:
            referrer_id = int(message.text.split("ref_")[1])
            if referrer_id != user_id:
                added = await add_referral(referrer_id, user_id)
                if added:
                    ref_count = await get_referral_count(referrer_id)
                    try:
                        await message.bot.send_message(
                            referrer_id,
                            f"🎉 Новый реферал!\n"
                            f"👤 {message.from_user.full_name}\n"
                            f"📊 {ref_count}/{REFERRALS_FOR_PREMIUM}",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass

                    if ref_count >= REFERRALS_FOR_PREMIUM:
                        is_prem = await is_premium_user(referrer_id)
                        if not is_prem:
                            await set_premium(referrer_id, True, days=30)
                            try:
                                await message.bot.send_message(
                                    referrer_id,
                                    "⭐ <b>Premium на 30 дней получен бесплатно!</b>",
                                    parse_mode="HTML"
                                )
                            except Exception:
                                pass

                    await save_user(
                        user_id,
                        message.from_user.username or "",
                        referred_by=referrer_id
                    )
        except Exception as e:
            print(f"Ref error: {e}")

    await save_user(user_id, message.from_user.username or "")

    await message.answer(
        "👁 <b>wexquize mode</b>\n\n"
        "Бот сохраняет удалённые и изменённые сообщения.\n\n"
        "📱 <b>Подключение:</b>\n"
        "Настройки → Telegram Business → Чат-боты\n\n"
        "Всё управление — в приложении 👇",
        parse_mode="HTML",
        reply_markup=app_keyboard()
    )


@router.message(Command("app"))
async def cmd_app(message: Message):
    await message.answer(
        "👁 <b>wexquize mode</b>",
        parse_mode="HTML",
        reply_markup=app_keyboard()
    )


@router.message(Command("ref"))
async def cmd_ref(message: Message):
    user_id = message.from_user.id
    ref_count = await get_referral_count(user_id)
    bot_me = await message.bot.me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{user_id}"
    await message.answer(
        f"🎁 <b>Реферальная программа</b>\n\n"
        f"👥 {ref_count}/{REFERRALS_FOR_PREMIUM}\n\n"
        f"🔗 <code>{ref_link}</code>\n\n"
        f"⭐ {REFERRALS_FOR_PREMIUM} рефералов = Premium 30 дней",
        parse_mode="HTML"
    )


# =========================
# ADMIN
# =========================
@router.message(Command("premium"))
async def cmd_premium_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer(
            "Всё в приложении 👇",
            reply_markup=app_keyboard()
        )
        return

    args = message.text.split()

    if len(args) >= 2 and args[1] != "remove":
        try:
            uid = int(args[1])
            days = int(args[2]) if len(args) >= 3 else 30
            await set_premium(uid, True, days=days)
            label = "♾️" if days == 0 else f"{days}д"
            await message.answer(f"✅ Premium {label} → {uid}")
            try:
                await message.bot.send_message(
                    uid,
                    "⭐ <b>Тебе выдан Premium!</b>",
                    parse_mode="HTML"
                )
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
        await message.answer(
            "/premium UID [DAYS]\n"
            "/premium remove UID\n"
            "/users"
        )


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

    for uid, uname, is_prem, conn_at, prem_until, ref_by in users:
        name = f"@{uname}" if uname else f"ID{uid}"
        s = "⭐" if is_prem else "🆓"
        try:
            d = datetime.fromisoformat(conn_at).strftime("%d.%m")
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


# =========================
# BUSINESS
# =========================
@router.business_connection()
async def on_business_connect(event: BusinessConnection):
    await save_user(event.user.id, event.user.username or "")
    try:
        if event.is_enabled:
            await event.bot.send_message(
                event.user.id,
                "✅ <b>wexquize mode подключён!</b>\n\n"
                "Сообщения сохраняются автоматически 🚀",
                parse_mode="HTML",
                reply_markup=app_keyboard()
            )
    except Exception as e:
        print(f"Connect error: {e}")


@router.business_message()
async def on_business_message(message: Message):
    try:
        if not message.business_connection_id:
            return

        await save_message(message, message.business_connection_id)

        if (message.photo or message.video or message.voice
                or message.video_note or message.document
                or message.sticker):
            await save_disappearing(message, message.business_connection_id)

    except Exception as e:
        print(f"Save error: {e}")


@router.edited_business_message()
async def on_business_edit(message: Message):
    try:
        if not message.business_connection_id:
            return

        old_msg = await get_message(
            message.message_id,
            message.chat.id,
            message.business_connection_id
        )
        if not old_msg:
            return

        old_text = old_msg[5]
        new_text = message.text or message.caption
        if old_text == new_text:
            return

        from_name = ""
        from_username = None
        if message.from_user:
            from_name = message.from_user.full_name
            from_username = message.from_user.username

        if from_username:
            display = f"@{from_username}"
        elif message.from_user:
            display = (
                f"<a href='tg://user?id={message.from_user.id}'>"
                f"{from_name}</a>"
            )
        else:
            display = from_name

        await save_edit(
            message.message_id, message.chat.id, from_name,
            old_text or "", new_text or "",
            message.business_connection_id
        )

        bc = await message.bot.get_business_connection(
            message.business_connection_id
        )
        owner_id = bc.user.id

        await message.bot.send_message(
            owner_id,
            f"✏️ <b>Редактирование</b>\n"
            f"👤 {display}\n\n"
            f"<b>Было:</b>\n"
            f"<blockquote>{old_text or '(пусто)'}</blockquote>\n\n"
            f"<b>Стало:</b>\n"
            f"<blockquote>{new_text or '(пусто)'}</blockquote>",
            parse_mode="HTML"
        )

        await save_message(message, message.business_connection_id)

    except Exception as e:
        print(f"Edit error: {e}")


@router.deleted_business_messages()
async def on_messages_deleted(event: BusinessMessagesDeleted):
    try:
        conn_id = event.business_connection_id
        bc = await event.bot.get_business_connection(conn_id)
        owner_id = bc.user.id

        for msg_id in event.message_ids:
            try:
                row = await get_message(msg_id, event.chat.id, conn_id)
                if not row:
                    continue

                (_, _, chat_id, from_id, from_name,
                 text, media_type, file_id, date, _) = row

                # Помечаем удалённым
                await mark_message_deleted(msg_id, event.chat.id, conn_id)

                # Не уведомляем если владелец удалил своё
                if from_id == owner_id:
                    continue

                # Имя отправителя
                username = await get_username_by_id(from_id) if from_id else None
                if username and username != "Unknown":
                    display = f"@{username}"
                elif from_id:
                    display = (
                        f"<a href='tg://user?id={from_id}'>"
                        f"{from_name}</a>"
                    )
                else:
                    display = from_name

                premium = await is_premium_user(owner_id)
                time_str = ""
                if date:
                    time_str = date[:16].replace('T', ' ')

                header = (
                    f"🗑️ <b>Удалено</b>\n"
                    f"👤 {display}\n"
                    f"🕐 {time_str}"
                )

                if media_type is None:
                    await event.bot.send_message(
                        owner_id,
                        header + f"\n\n<blockquote>"
                        f"{text or '(пусто)'}</blockquote>",
                        parse_mode="HTML"
                    )

                elif premium:
                    try:
                        if media_type == "photo":
                            await event.bot.send_photo(
                                owner_id, file_id,
                                caption=header, parse_mode="HTML"
                            )
                        elif media_type == "video":
                            await event.bot.send_video(
                                owner_id, file_id,
                                caption=header, parse_mode="HTML"
                            )
                        elif media_type == "voice":
                            await event.bot.send_voice(
                                owner_id, file_id,
                                caption=header, parse_mode="HTML"
                            )
                        elif media_type == "document":
                            await event.bot.send_document(
                                owner_id, file_id,
                                caption=header, parse_mode="HTML"
                            )
                        elif media_type == "sticker":
                            await event.bot.send_message(
                                owner_id, header, parse_mode="HTML"
                            )
                            await event.bot.send_sticker(
                                owner_id, file_id
                            )
                        elif media_type == "video_note":
                            await event.bot.send_message(
                                owner_id, header, parse_mode="HTML"
                            )
                            await event.bot.send_video_note(
                                owner_id, file_id
                            )
                    except Exception:
                        await event.bot.send_message(
                            owner_id,
                            header + f"\n\n📎 {media_type}",
                            parse_mode="HTML"
                        )

                else:
                    emoji_map = {
                        "photo": "📸", "video": "🎥",
                        "voice": "🎤", "document": "📁",
                        "sticker": "🎭", "video_note": "📹"
                    }
                    e = emoji_map.get(media_type, "📎")
                    await event.bot.send_message(
                        owner_id,
                        header + f"\n\n{e} Медиа · Откройте приложение",
                        parse_mode="HTML",
                        reply_markup=app_keyboard()
                    )

            except Exception as e:
                print(f"Del {msg_id} error: {e}")

    except Exception as e:
        print(f"Deleted error: {e}")

from aiogram import Router
from aiogram.types import Message, BusinessConnection, BusinessMessagesDeleted
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
    get_username_by_id
)
from config import ADMIN_ID, REFERRALS_FOR_PREMIUM
from datetime import datetime

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id

    if message.text and message.text.startswith("/start ref_"):
        try:
            referrer_id = int(message.text.split("ref_")[1])
            if referrer_id != user_id:
                if add_referral(referrer_id, user_id):
                    ref_count = get_referral_count(referrer_id)
                    await message.bot.send_message(
                        referrer_id,
                        f"🎉 <b>Новый реферал!</b>\n\n"
                        f"👤 {message.from_user.full_name} подключил бота!\n"
                        f"📊 Рефералов: {ref_count}/{REFERRALS_FOR_PREMIUM}",
                        parse_mode="HTML"
                    )
                    if ref_count >= REFERRALS_FOR_PREMIUM and not is_premium_user(referrer_id):
                        set_premium(referrer_id, True, days=30)
                        await message.bot.send_message(
                            referrer_id,
                            "⭐ <b>Поздравляем! Ты получил Premium на 30 дней бесплатно!</b> 🎁",
                            parse_mode="HTML"
                        )
                    save_user(user_id, message.from_user.username or "", referred_by=referrer_id)
        except:
            pass

    save_user(user_id, message.from_user.username or "")
    await message.answer(
        "👁 <b>wexquize mode — бот для сохранения удалённых сообщений</b>\n\n"
        "📱 <b>Инструкция по подключению:</b>\n\n"
        "1️⃣ Открой <b>Настройки профиля</b> в Telegram\n"
        "2️⃣ Найди раздел <b>«Автоматизация чатов»</b>\n"
        "3️⃣ Нажми <b>«Добавить бота»</b>\n"
        "4️⃣ Выбери этого бота из списка\n"
        "5️⃣ Подтверди подключение\n\n"
        "✨ После подключения бот автоматически начнёт сохранять все входящие сообщения.\n\n"
        "🔒 <b>Как это работает:</b>\n"
        "• Все сообщения сохраняются автоматически\n"
        "• Редактирования отслеживаются\n"
        "• Если кто-то удалит сообщение — я пришлю тебе копию\n\n"
        "💎 Для изучения доступных тарифов введи команду /premium",
        parse_mode="HTML"
    )


@router.message(Command("ref"))
async def cmd_ref(message: Message):
    user_id = message.from_user.id
    ref_count = get_referral_count(user_id)
    bot_username = (await message.bot.me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    await message.answer(
        f"🎁 <b>Реферальная программа</b>\n\n"
        f"👥 Приглашено: {ref_count}/{REFERRALS_FOR_PREMIUM}\n\n"
        f"🔗 <b>Ссылка:</b>\n<code>{ref_link}</code>\n\n"
        f"⭐ После {REFERRALS_FOR_PREMIUM} рефералов получишь Premium на 30 дней!",
        parse_mode="HTML"
    )


@router.message(Command("premium"))
async def cmd_premium(message: Message):
    if message.from_user.id == ADMIN_ID:
        args = message.text.split()
        
        # /premium USER_ID [DAYS] - выдать (0 = бесконечно)
        if len(args) >= 2 and args[1] != "remove":
            try:
                uid = int(args[1])
                days = int(args[2]) if len(args) == 3 else 30
                
                set_premium(uid, True, days=days)
                
                # Уведомляем админа
                if days == 0:
                    await message.answer(f"✅ Бесконечный Premium выдан пользователю {uid}")
                    premium_text = "бесконечный Premium"
                else:
                    await message.answer(f"✅ Premium на {days} дней выдан пользователю {uid}")
                    premium_text = f"Premium на {days} дней"
                
                # Уведомляем пользователя
                try:
                    await message.bot.send_message(
                        uid,
                        f"⭐ <b>Поздравляем!</b>\n\n"
                        f"Тебе выдан {premium_text}! 🎁\n\n"
                        f"Теперь доступны:\n"
                        f"📸 Фото и видео\n"
                        f"📁 Документы\n"
                        f"🎤 Голосовые\n"
                        f"🎭 Стикеры",
                        parse_mode="HTML"
                    )
                except:
                    await message.answer("⚠️ Не удалось уведомить пользователя")
                    
            except ValueError:
                await message.answer("❌ Неверный формат. Используй: /premium USER_ID [DAYS]")
        
        # /premium remove USER_ID - отобрать
        elif len(args) == 3 and args[1] == "remove":
            try:
                uid = int(args[2])
                remove_premium(uid)
                
                # Уведомляем админа
                await message.answer(f"✅ Premium отобран у пользователя {uid}")
                
                # Уведомляем пользователя
                try:
                    await message.bot.send_message(
                        uid,
                        "❌ <b>Ваша подписка была обнулена</b>\n\n"
                        "Если вы считаете, что её обнулили по ошибке, "
                        "напишите владельцу бота: @wexquize",
                        parse_mode="HTML"
                    )
                except:
                    await message.answer("⚠️ Не удалось уведомить пользователя")
                    
            except ValueError:
                await message.answer("❌ Неверный ID")
        else:
            await message.answer(
                "ℹ️ <b>Команды админа:</b>\n\n"
                "/premium USER_ID [DAYS] — выдать Premium\n"
                "  (0 дней = бесконечный)\n"
                "/premium remove USER_ID — отобрать Premium\n"
                "/users — список всех пользователей",
                parse_mode="HTML"
            )
    else:
        premium_info = get_premium_info(message.from_user.id)
        
        if premium_info and premium_info['active']:
            if premium_info.get('permanent'):
                await message.answer("⭐ <b>У тебя бесконечный Premium!</b> ♾️", parse_mode="HTML")
            elif premium_info['days_left'] is not None:
                await message.answer(
                    f"⭐ <b>У тебя есть Premium!</b>\n\n"
                    f"📅 Осталось дней: {premium_info['days_left']}",
                    parse_mode="HTML"
                )
            else:
                await message.answer("⭐ У тебя есть Premium!")
        else:
            await message.answer(
                "⭐ <b>wexquize mode Premium</b>\n\n"
                "🆓 <b>Бесплатная версия:</b>\n"
                "• Текстовые сообщения\n\n"
                "💎 <b>Premium версия:</b>\n"
                "• Фото и видео\n"
                "• Файлы и документы\n"
                "• Голосовые сообщения\n"
                "• Стикеры\n\n"
                "💰 <b>Приобрести:</b> @wexquize\n"
                "🎁 <b>Получить бесплатно:</b> /ref",
                parse_mode="HTML"
            )


@router.message(Command("users"))
async def cmd_users(message: Message):
    """Список всех пользователей (только для админа)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    users = get_all_users_info()
    
    if not users:
        await message.answer("📝 Пользователей пока нет")
        return
    
    total_users = len(users)
    premium_users = sum(1 for u in users if u[2])
    free_users = total_users - premium_users
    
    text = (
        f"👥 <b>СПИСОК ПОЛЬЗОВАТЕЛЕЙ</b>\n"
        f"═══════════════════════════════\n"
        f"📊 Всего: {total_users}\n"
        f"⭐ Premium: {premium_users}\n"
        f"🆓 Free: {free_users}\n"
        f"═══════════════════════════════\n\n"
    )
    
    for user_id, username, is_premium, connected_at, premium_until, referred_by in users:
        # Статус
        if is_premium:
            if premium_until == "permanent":
                status = "⭐ Premium ♾️"
            elif premium_until:
                try:
                    until = datetime.fromisoformat(premium_until)
                    days_left = (until - datetime.now()).days
                    status = f"⭐ Premium ({days_left}д)"
                except:
                    status = "⭐ Premium"
            else:
                status = "⭐ Premium"
        else:
            status = "🆓 Free"
        
        # Дата подключения
        try:
            connected = datetime.fromisoformat(connected_at)
            date_str = connected.strftime("%d.%m.%Y")
        except:
            date_str = "?"
        
        # Реферал
        if referred_by:
            referrer_name = get_username_by_id(referred_by)
            ref_info = f"@{referrer_name}" if referrer_name != "Unknown" else f"ID{referred_by}"
        else:
            ref_info = "—"
        
        # Имя пользователя
        if username:
            display_name = f"@{username}"
        else:
            display_name = f"ID{user_id}"
        
        # Формируем строку
        user_line = (
            f"<b>{display_name}</b>\n"
            f"├ ID: <code>{user_id}</code>\n"
            f"├ {status}\n"
            f"├ 📅 {date_str}\n"
            f"└ Реф: {ref_info}\n\n"
        )
        
        if len(text + user_line) > 4000:
            await message.answer(text, parse_mode="HTML")
            text = user_line
        else:
            text += user_line
    
    if text:
        await message.answer(text, parse_mode="HTML")


@router.business_connection()
async def on_business_connect(event: BusinessConnection):
    save_user(event.user.id, event.user.username or "", is_premium=False)
    try:
        if event.is_enabled:
            await event.bot.send_message(
                event.user.id,
                "✅ <b>wexquize mode подключён!</b>\n\n"
                "Теперь я сохраняю все сообщения 🚀\n\n"
                "/premium — изучить тарифы\n"
                "/ref — реферальная программа",
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"Ошибка подключения: {e}")


@router.business_message()
async def on_business_message(message: Message):
    try:
        if not message.business_connection_id:
            return

        save_message(message, message.business_connection_id)

        if (message.photo or message.video or message.voice
                or message.video_note or message.document or message.sticker):
            save_disappearing(message, message.business_connection_id)

        print(f"✅ Сохранено: msg_id={message.message_id}")

    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")


@router.edited_business_message()
async def on_business_edit(message: Message):
    try:
        if not message.business_connection_id:
            return

        old_msg = get_message(message.message_id, message.chat.id, message.business_connection_id)
        if not old_msg:
            return

        old_text = old_msg[5]
        new_text = message.text or message.caption

        if old_text == new_text:
            return

        from_name = message.from_user.full_name if message.from_user else "Неизвестно"
        from_username = message.from_user.username if message.from_user else None
        
        # Формируем имя для отображения (юзернейм или ID)
        if from_username:
            display_name = f"@{from_username}"
        else:
            display_name = f"<a href='tg://user?id={message.from_user.id}'>{from_name}</a>"
        
        save_edit(message.message_id, message.chat.id, from_name,
                  old_text or "", new_text or "", message.business_connection_id)

        bc = await message.bot.get_business_connection(message.business_connection_id)
        owner_id = bc.user.id

        await message.bot.send_message(
            owner_id,
            f"✏️ <b>ОТРЕДАКТИРОВАНО</b>\n"
            f"───────────────────\n"
            f"👤 {display_name}\n"
            f"───────────────────\n\n"
            f"<b>Было:</b>\n<blockquote>{old_text or '(пусто)'}</blockquote>\n\n"
            f"<b>Стало:</b>\n<blockquote>{new_text or '(пусто)'}</blockquote>",
            parse_mode="HTML"
        )

        save_message(message, message.business_connection_id)

    except Exception as e:
        print(f"❌ Ошибка редактирования: {e}")


@router.deleted_business_messages()
async def on_messages_deleted(event: BusinessMessagesDeleted):
    try:
        conn_id = event.business_connection_id
        bc = await event.bot.get_business_connection(conn_id)
        owner_id = bc.user.id

        for msg_id in event.message_ids:
            try:
                row = get_message(msg_id, event.chat.id, conn_id)
                if not row:
                    continue

                _, _, chat_id, from_id, from_name, text, media_type, file_id, date, _ = row

                # ПРОВЕРКА: не отправляем если владелец удалил свое сообщение
                if from_id == owner_id:
                    print(f"⏭️ Пропуск: владелец удалил своё сообщение {msg_id}")
                    continue

                # Получаем информацию о пользователе из базы
                from database import get_username_by_id
                username = get_username_by_id(from_id) if from_id else None
                
                # Формируем имя для отображения (юзернейм или кликабельный ID)
                if username and username != "Unknown":
                    display_name = f"@{username}"
                elif from_id:
                    display_name = f"<a href='tg://user?id={from_id}'>{from_name}</a>"
                else:
                    display_name = from_name

                premium = is_premium_user(owner_id)
                time_str = date[:16].replace('T', ' ')

                header = (
                    f"🗑️ <b>УДАЛЕНО</b>\n"
                    f"───────────────────\n"
                    f"👤 {display_name}\n"
                    f"🕐 {time_str}\n"
                    f"───────────────────"
                )

                if media_type is None:
                    await event.bot.send_message(
                        owner_id,
                        header + f"\n\n<blockquote>{text or '(пусто)'}</blockquote>",
                        parse_mode="HTML"
                    )
                elif premium:
                    if media_type == "photo":
                        await event.bot.send_photo(owner_id, file_id, caption=header, parse_mode="HTML")
                    elif media_type == "video":
                        await event.bot.send_video(owner_id, file_id, caption=header, parse_mode="HTML")
                    elif media_type == "voice":
                        await event.bot.send_voice(owner_id, file_id, caption=header, parse_mode="HTML")
                    elif media_type == "document":
                        await event.bot.send_document(owner_id, file_id, caption=header, parse_mode="HTML")
                    elif media_type == "sticker":
                        await event.bot.send_message(owner_id, header, parse_mode="HTML")
                        await event.bot.send_sticker(owner_id, file_id)
                    elif media_type == "video_note":
                        await event.bot.send_message(owner_id, header, parse_mode="HTML")
                        await event.bot.send_video_note(owner_id, file_id)
                else:
                    emoji_map = {
                        "photo": "📸",
                        "video": "🎥",
                        "voice": "🎤",
                        "document": "📁",
                        "sticker": "🎭",
                        "video_note": "📹"
                    }
                    emoji = emoji_map.get(media_type, "📎")
                    await event.bot.send_message(
                        owner_id,
                        header + f"\n\n{emoji} Медиа недоступно\n💎 /premium",
                        parse_mode="HTML"
                    )

            except Exception as e:
                print(f"❌ Ошибка удаления {msg_id}: {e}")
    except Exception as e:
        print(f"❌ Ошибка deleted: {e}")
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

MINIAPP_URL = "https://wexquize.github.io/wexbot/"

@router.message(Command("app"))
async def cmd_app(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="👁 Открыть wexquize mode",
            web_app=WebAppInfo(url=MINIAPP_URL)
        )
    ]])
    await message.answer(
        "👁 <b>wexquize mode App</b>\n\n"
        "Статистика, история и ИИ — всё здесь.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

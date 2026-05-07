import asyncio
import logging
import sqlite3
import os  # Добавили для порта
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, FREE_DAYS, PREMIUM_DAYS
from database import init_db, check_expired_premiums, get_all_users_info
from handlers import router
from aiohttp import web  # Нужно добавить в requirements.txt

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- ЧАСТЬ ДЛЯ RENDER (ВЕБ-СЕРВЕР) ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render дает порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Веб-сервер запущен на порту {port}")

# --- ТВОИ ФУНКЦИИ БЕЗ ИЗМЕНЕНИЙ ---
async def cleanup_old_messages():
    while True:
        try:
            conn = sqlite3.connect('messages.db')
            c = conn.cursor()
            free_date = (datetime.now() - timedelta(days=FREE_DAYS)).isoformat()
            c.execute("""
                DELETE FROM messages 
                WHERE date < ? AND from_user_id IN (
                    SELECT user_id FROM users WHERE is_premium=0
                )
            """, (free_date,))
            premium_date = (datetime.now() - timedelta(days=PREMIUM_DAYS)).isoformat()
            c.execute("""
                DELETE FROM messages 
                WHERE date < ? AND from_user_id IN (
                    SELECT user_id FROM users WHERE is_premium=1
                )
            """, (premium_date,))
            c.execute("DELETE FROM disappearing WHERE date < ?", (premium_date,))
            conn.commit()
            deleted = c.rowcount
            conn.close()
            if deleted > 0:
                logger.info(f"✅ Удалено {deleted} старых записей")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки: {e}")
        await asyncio.sleep(86400)

async def check_premiums(bot: Bot):
    while True:
        try:
            conn = sqlite3.connect('messages.db')
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute("""
                SELECT user_id FROM users 
                WHERE is_premium=1 
                AND premium_until < ? 
                AND premium_until != 'permanent'
            """, (now,))
            expired_users = [row[0] for row in c.fetchall()]
            conn.close()
            expired = check_expired_premiums()
            for user_id in expired_users:
                try:
                    await bot.send_message(
                        user_id,
                        "⏰ <b>Ваша Premium подписка истекла</b>\n\n"
                        "Чтобы продлить:\n"
                        "💰 Купить: @wexquize\n"
                        "🎁 Бесплатно: /ref — пригласи 5 друзей!",
                        parse_mode="HTML"
                    )
                    logger.info(f"📧 Уведомление об истечении отправлено {user_id}")
                except Exception as e:
                    logger.error(f"❌ Не удалось уведомить {user_id}: {e}")
            if expired > 0:
                logger.info(f"⏰ Истекло подписок: {expired}")
        except Exception as e:
            logger.error(f"❌ Ошибка проверки подписок: {e}")
        await asyncio.sleep(3600)

async def main():
    logger.info("📦 Инициализация базы данных...")
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # ЗАПУСКАЕМ ВЕБ-СЕРВЕР ДЛЯ RENDER
    await start_web_server()

    logger.info("✅ Бот запущен!")

    asyncio.create_task(cleanup_old_messages())
    asyncio.create_task(check_premiums(bot))

    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⛔ Бот остановлен")
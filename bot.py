import asyncio
import os
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, API_PORT
from handlers import router
from database import init_db


async def start_api():
    try:
        from api import create_app
        from aiohttp import web

        app = await create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', API_PORT)
        await site.start()
        print(f"✅ API запущен на порту {API_PORT}")
    except Exception as e:
        print(f"⚠️ API ошибка: {e}")
        import traceback
        traceback.print_exc()


async def main():
    # Проверка переменных окружения
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан!")
        return

    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL не задан!")
        return

    # Инициализация базы данных
    try:
        await init_db()
    except Exception as e:
        print(f"❌ Ошибка инициализации БД: {e}")
        import traceback
        traceback.print_exc()
        return

    # Создаём бота
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Удаляем webhook на случай если был установлен
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook очищен")
    except Exception as e:
        print(f"⚠️ Webhook: {e}")

    # Запускаем API
    await start_api()

    print("🤖 Бот запущен и слушает обновления...")

    # Polling
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    except Exception as e:
        print(f"❌ Polling error: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⛔ Остановлен")

import asyncio
import os
import aiohttp
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, API_PORT
from handlers import router
from database import init_db


async def self_ping():
    url = f"https://wexbot.onrender.com/health"
    await asyncio.sleep(60)  # первый пинг через минуту
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as r:
                    print(f"🏓 Ping: {r.status}")
        except Exception as e:
            print(f"⚠️ Ping err: {e}")
        await asyncio.sleep(240)  # каждые 4 минуты


async def start_api():
    try:
        from api import create_app
        from aiohttp import web

        app = await create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', API_PORT)
        await site.start()
        print(f"✅ API на порту {API_PORT}")
    except Exception as e:
        print(f"⚠️ API ошибка: {e}")
        import traceback
        traceback.print_exc()


async def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не задан!")
        return

    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL не задан!")
        return

    try:
        await init_db()
    except Exception as e:
        print(f"❌ БД ошибка: {e}")
        import traceback
        traceback.print_exc()
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Webhook очищен")
    except Exception as e:
        print(f"⚠️ Webhook: {e}")

    await start_api()

    # Запускаем self-ping чтобы Render не засыпал
    asyncio.create_task(self_ping())

    print("🤖 Бот запущен")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )
    except Exception as e:
        print(f"❌ Polling: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⛔ Остановлен")

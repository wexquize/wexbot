import asyncio
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
        print(f"✅ API на порту {API_PORT}")
    except Exception as e:
        print(f"⚠️ API ошибка: {e}")


async def main():
    init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await start_api()

    print("🤖 Бот запущен")
    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types()
    )


if __name__ == "__main__":
    asyncio.run(main())

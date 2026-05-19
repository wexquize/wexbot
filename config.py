import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
REFERRALS_FOR_PREMIUM = 3
MINIAPP_URL = "https://wexquize.github.io/wexbot/"
API_PORT = int(os.getenv("PORT", "8080"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "wexbot")

# DEBUG — временно для проверки
print(f"DEBUG TOKEN: '{BOT_TOKEN[:15]}...' длина={len(BOT_TOKEN)}")
print(f"DEBUG ADMIN_ID: {ADMIN_ID}")
print(f"DEBUG все env переменные начинающиеся с BOT:")
for key in os.environ:
    if 'BOT' in key.upper() or 'TOKEN' in key.upper() or 'ADMIN' in key.upper():
        val = os.environ[key]
        print(f"  {key} = '{val[:15]}...' длина={len(val)}")

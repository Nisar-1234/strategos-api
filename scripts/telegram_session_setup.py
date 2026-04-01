"""
One-time helper: authenticate with Telegram and print TELEGRAM_SESSION_STRING.

Usage (from repo root, with .env or env vars set):
  set TELEGRAM_API_ID=...
  set TELEGRAM_API_HASH=...
  python scripts/telegram_session_setup.py

Paste the printed TELEGRAM_SESSION_STRING into .env on the server.
Do not commit the session string or .env.
"""

import asyncio
import os


async def main() -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = (os.environ.get("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or "").strip()
    if not api_id or not api_hash:
        print("Set TELEGRAM_API_ID and TELEGRAM_API_HASH (from https://my.telegram.org/apps)")
        raise SystemExit(1)

    async with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        await client.start()
        sess = client.session.save()
        print("\nAdd to .env:\n")
        print(f"TELEGRAM_SESSION_STRING={sess}\n")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Telethon Interactive Login Script

This script performs the initial Telethon authentication to generate a session file.
Run this once before starting the bot to authenticate with Telegram.

Usage:
    python scripts/telethon_login.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from telethon import TelegramClient


async def main():
    settings = get_settings()
    
    print("=" * 60)
    print("Telethon Login for Anime Tracker Bot")
    print("=" * 60)
    print(f"API ID: {settings.API_ID}")
    print(f"Session: {settings.SESSION_NAME}.session")
    print(f"Monitor Group: {settings.MONITOR_GROUP}")
    print("=" * 60)
    
    client = TelegramClient(
        settings.SESSION_NAME,
        settings.API_ID,
        settings.API_HASH
    )
    
    await client.start()
    
    me = await client.get_me()
    print(f"\n✅ Successfully logged in as: {me.first_name} {me.last_name or ''} (@{me.username or 'no username'})")
    print(f"User ID: {me.id}")
    print(f"Session saved to: {settings.SESSION_NAME}.session")
    
    # Verify we can access the monitor group
    try:
        entity = await client.get_entity(settings.MONITOR_GROUP)
        print(f"✅ Monitor group '{settings.MONITOR_GROUP}' found: {entity.title} (ID: {entity.id})")
    except Exception as e:
        print(f"⚠️  Could not access monitor group '{settings.MONITOR_GROUP}': {e}")
        print("   Make sure the bot is added to this group/channel!")
    
    await client.disconnect()
    print("\n🎉 Login complete! You can now run the bot.")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
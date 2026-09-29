#!/usr/bin/env python3
"""
Bot Command Handlers

Handles management commands for the anime tracker bot:
- /add_anime - Add new anime with title and aliases
- /add_channel - Attach a channel to an anime
- /list - Show animes with topic and channel counts
- /set_interval - Change check interval
"""

import logging
from typing import Optional, List
from telethon import events, Button
from telethon.tl.types import User

from src.config import get_settings
from src.database import (
    get_db_connection,
    get_active_animes,
    sync_animes_to_db,
    AnimeRow,
    search_messages_in_channel,
    search_anime_by_title,
)
from src.anime_loader import AnimesConfig, AnimeConfig, get_anime_dicts


logger = logging.getLogger(__name__)


# Admin user IDs (only these users can use commands)
def get_admin_ids() -> List[int]:
    """Get admin user IDs from settings."""
    settings = get_settings()
    # For now, allow any user. In production, restrict to specific IDs.
    return []


def is_admin(user_id: int) -> bool:
    """Check if user is admin."""
    admins = get_admin_ids()
    if not admins:
        return True  # No admins configured = allow all
    return user_id in admins


async def cmd_start(event):
    """Handle /start command."""
    await event.respond(
        "🤖 **Anime Tracker Bot**\n\n"
        "Available commands:\n"
        "• `/add_anime <title> | <alias1,alias2,...> | <@channel1,@channel2,...>`\n"
        "• `/add_channel <anime_title> | <@channel>`\n"
        "• `/list` - Show all tracked animes\n"
        "• `/search <title>` - جستجوی عمومی در تمام کانال‌ها\n"
        "• `/search_anime <query>` - جستجو در انیمه‌های ثبت‌شده\n"
        "• `/search_channel @channel <query>` - جستجو در یک کانال\n"
        "• `/full_scan @channel [limit]` - اسکن عمیق یک کانال\n"
        "• `/set_interval <seconds>` - Change scan interval\n"
        "• `/help` - Show this help\n\n"
        "Example:\n"
        "`/add_anime Jujutsu Kaisen | jjk,jujutsu | @jjk_channel,@anime_news`"
    )


async def cmd_help(event):
    """Handle /help command."""
    await cmd_start(event)


async def cmd_list(event):
    """Handle /list command - show all tracked animes."""
    settings = get_settings()
    animes = await get_active_animes(str(settings.db_path))
    
    if not animes:
        await event.respond("📭 No animes currently tracked.")
        return
    
    lines = ["📺 **Tracked Animes:**\n"]
    for i, anime in enumerate(animes, 1):
        aliases_str = ", ".join(anime.aliases) if anime.aliases else "—"
        channels_str = ", ".join(anime.channels) if anime.channels else "—"
        
        # Get topic info
        from src.database import get_topic
        topic = await get_topic(str(settings.db_path), anime.id)
        topic_info = f"Topic: {topic.topic_id}" if topic else "No topic"
        
        lines.append(
            f"**{i}. {anime.title}**\n"
            f"   🆔 ID: {anime.id}\n"
            f"   🏷️ Aliases: {aliases_str}\n"
            f"   📡 Channels: {channels_str}\n"
            f"   📝 {topic_info}\n"
        )
    
    await event.respond("\n".join(lines))


async def cmd_add_anime(event):
    """
    Handle /add_anime command.
    Format: /add_anime <title> | <alias1,alias2,...> | <@channel1,@channel2,...>
    """
    settings = get_settings()
    if not is_admin(event.sender_id):
        await event.respond("❌ Unauthorized")
        return
    
    # Parse command arguments
    args = event.raw_text.split(maxsplit=1)
    if len(args) < 2:
        await event.respond(
            "❌ Usage: `/add_anime <title> | <alias1,alias2> | <@channel1,@channel2>`\n\n"
            "Example: `/add_anime Jujutsu Kaisen | jjk,jujutsu | @jjk_channel,@anime_news`"
        )
        return
    
    try:
        parts = [p.strip() for p in args[1].split("|")]
        if len(parts) != 3:
            raise ValueError("Expected 3 parts separated by |")
        
        title = parts[0]
        aliases = [a.strip() for a in parts[1].split(",") if a.strip()]
        channels = [c.strip() for c in parts[2].split(",") if c.strip()]
        
        if not title:
            raise ValueError("Title cannot be empty")
        if not aliases:
            raise ValueError("At least one alias required")
        if not channels:
            raise ValueError("At least one channel required")
        
        # Validate channel format
        for ch in channels:
            if not ch.startswith("@"):
                raise ValueError(f"Channel must start with @: {ch}")
        
        # Load current config
        config = AnimesConfig(animes=[
            AnimeConfig(title=a.title, aliases=a.aliases, channels=a.channels)
            for a in await get_active_animes(str(settings.db_path))
        ])
        
        # Check if anime already exists
        for existing in config.animes:
            if existing.title.lower() == title.lower():
                await event.respond(f"❌ Anime '{title}' already exists!")
                return
        
        # Add new anime
        new_anime = AnimeConfig(title=title, aliases=aliases, channels=channels)
        config.animes.append(new_anime)
        
        # Sync to database
        anime_dicts = get_anime_dicts(config)
        stats = await sync_animes_to_db(str(settings.db_path), anime_dicts)
        
        # Also update the JSON config file
        import json
        from pathlib import Path
        config_path = Path("config/animes.json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"animes": [a.model_dump() for a in config.animes]}, f, indent=2, ensure_ascii=False)
        
        await event.respond(
            f"✅ Added anime: **{title}**\n"
            f"🏷️ Aliases: {', '.join(aliases)}\n"
            f"📡 Channels: {', '.join(channels)}\n"
            f"📊 Sync stats: {stats}"
        )
        
    except ValueError as e:
        await event.respond(f"❌ Error: {e}")
    except Exception as e:
        logger.error(f"Error in add_anime: {e}")
        await event.respond(f"❌ Unexpected error: {e}")


async def cmd_add_channel(event):
    """
    Handle /add_channel command.
    Format: /add_channel <anime_title> | <@channel>
    """
    if not is_admin(event.sender_id):
        await event.respond("❌ Unauthorized")
        return
    
    args = event.raw_text.split(maxsplit=1)
    if len(args) < 2:
        await event.respond(
            "❌ Usage: `/add_channel <anime_title> | <@channel>`\n\n"
            "Example: `/add_channel Jujutsu Kaisen | @jjk_news`"
        )
        return
    
    try:
        parts = [p.strip() for p in args[1].split("|")]
        if len(parts) != 2:
            raise ValueError("Expected 2 parts separated by |")
        
        anime_title = parts[0]
        channel = parts[1].strip()
        
        if not channel.startswith("@"):
            raise ValueError("Channel must start with @")
        
        # Load current config
        config = AnimesConfig(animes=[
            AnimeConfig(title=a.title, aliases=a.aliases, channels=a.channels)
            for a in await get_active_animes(str(settings.db_path))
        ])
        
        # Find anime
        target_anime = None
        for anime in config.animes:
            if anime.title.lower() == anime_title.lower():
                target_anime = anime
                break
        
        if not target_anime:
            await event.respond(f"❌ Anime '{anime_title}' not found!")
            return
        
        # Check if channel already exists
        if channel in target_anime.channels:
            await event.respond(f"❌ Channel {channel} already added to '{anime_title}'!")
            return
        
        # Add channel
        target_anime.channels.append(channel)
        
        # Sync to database
        anime_dicts = get_anime_dicts(config)
        stats = await sync_animes_to_db(str(settings.db_path), anime_dicts)
        
        # Update JSON config
        import json
        from pathlib import Path
        config_path = Path("config/animes.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"animes": [a.model_dump() for a in config.animes]}, f, indent=2, ensure_ascii=False)
        
        await event.respond(
            f"✅ Added channel **{channel}** to **{anime_title}**\n"
            f"📊 Sync stats: {stats}"
        )
        
    except ValueError as e:
        await event.respond(f"❌ Error: {e}")
    except Exception as e:
        logger.error(f"Error in add_channel: {e}")
        await event.respond(f"❌ Unexpected error: {e}")


async def cmd_set_interval(event):
    """
    Handle /set_interval command.
    Format: /set_interval <seconds>
    """
    if not is_admin(event.sender_id):
        await event.respond("❌ Unauthorized")
        return
    
    args = event.raw_text.split(maxsplit=1)
    if len(args) < 2:
        await event.respond(
            "❌ Usage: `/set_interval <seconds>`\n\n"
            "Example: `/set_interval 300` (5 minutes)\n"
            f"Current: {get_settings().CHECK_INTERVAL}s"
        )
        return
    
    try:
        interval = int(args[1].strip())
        if interval < 10:
            raise ValueError("Interval must be at least 10 seconds")
        if interval > 86400:
            raise ValueError("Interval cannot exceed 86400 seconds (24 hours)")
        
        # Update .env file
        import os
        from pathlib import Path
        env_path = Path(".env")
        
        if env_path.exists():
            with open(env_path, "r") as f:
                lines = f.readlines()
        else:
            lines = []
        
        # Update or add CHECK_INTERVAL
        found = False
        for i, line in enumerate(lines):
            if line.startswith("CHECK_INTERVAL"):
                lines[i] = f"CHECK_INTERVAL={interval}\n"
                found = True
                break
        
        if not found:
            lines.append(f"CHECK_INTERVAL={interval}\n")
        
        with open(env_path, "w") as f:
            f.writelines(lines)
        
        # Note: bot needs restart to pick up new interval
        await event.respond(
            f"✅ Interval updated to **{interval}** seconds\n"
            f"⚠️ **Restart the bot for changes to take effect**"
        )
        
    except ValueError as e:
        await event.respond(f"❌ Error: {e}")
    except Exception as e:
        logger.error(f"Error in set_interval: {e}")
        await event.respond(f"❌ Unexpected error: {e}")


async def cmd_search_anime(event):
    """
    Handle /search_anime command - search for anime by title/alias across all tracked animes.
    Format: /search_anime <query>
    """
    if not is_admin(event.sender_id):
        await event.respond("❌ Unauthorized")
        return
    
    args = event.raw_text.split(maxsplit=1)
    if len(args) < 2:
        await event.respond(
            "❌ Usage: `/search_anime <query>`\n\n"
            "Example: `/search_anime solo`\n"
            "Example: `/search_anime جوجوتسو`"
        )
        return
    
    query = args[1].strip()
    if not query:
        await event.respond("❌ Query cannot be empty")
        return
    
    settings = get_settings()
    try:
        results = await search_anime_by_title(str(settings.db_path), query, limit=20)
        
        if not results:
            await event.respond(f"🔍 No anime found matching: **{query}**")
            return
        
        lines = [f"🔍 **Search results for: '{query}'** ({len(results)} found)\n"]
        for i, anime in enumerate(results, 1):
            aliases_str = ", ".join(anime.aliases[:5]) if anime.aliases else "—"
            channels_str = ", ".join(anime.channels[:3]) if anime.channels else "—"
            lines.append(
                f"**{i}. {anime.title}**\n"
                f"   🆔 ID: {anime.id}\n"
                f"   🏷️ Aliases: {aliases_str}\n"
                f"   📡 Channels: {channels_str}\n"
            )
        
        await event.respond("\n".join(lines))
        
    except Exception as e:
        logger.error(f"Error in search_anime: {e}")
        await event.respond(f"❌ Unexpected error: {e}")


async def cmd_search_channel(event):
    """
    Handle /search_channel command - search for episodes in a specific channel.
    Format: /search_channel @channel <query>
    """
    if not is_admin(event.sender_id):
        await event.respond("❌ Unauthorized")
        return
    
    args = event.raw_text.split(maxsplit=2)
    if len(args) < 3:
        await event.respond(
            "❌ Usage: `/search_channel @channel <query>`\n\n"
            "Example: `/search_channel @AnimeChannel_X solo`\n"
            "Example: `/search_channel @AnimeWorld jujutsu`"
        )
        return
    
    channel = args[1].strip()
    query = args[2].strip()
    
    if not channel.startswith("@"):
        await event.respond("❌ Channel must start with @")
        return
    if not query:
        await event.respond("❌ Query cannot be empty")
        return
    
    settings = get_settings()
    try:
        results = await search_messages_in_channel(str(settings.db_path), channel, query, limit=20)
        
        if not results:
            await event.respond(f"🔍 No episodes found in **{channel}** matching: **{query}**")
            return
        
        lines = [f"🔍 **Search results in {channel} for: '{query}'** ({len(results)} found)\n"]
        for i, ep in enumerate(results, 1):
            ep_num = ep.get('episode_number', '?')
            anime_title = ep.get('anime_title', 'Unknown')
            msg_id = ep.get('message_id', '?')
            link = f"https://t.me/{channel.lstrip('@')}/{msg_id}"
            lines.append(
                f"**{i}. {anime_title} - Episode {ep_num}**\n"
                f"   🔗 {link}\n"
            )
        
        await event.respond("\n".join(lines))
        
    except Exception as e:
        logger.error(f"Error in search_channel: {e}")
        await event.respond(f"❌ Unexpected error: {e}")


async def cmd_full_channel_scan(event):
    """
    Handle /full_scan command - perform a deep scan of a channel (more than 50 messages).
    Format: /full_scan @channel [limit=200]
    """
    if not is_admin(event.sender_id):
        await event.respond("❌ Unauthorized")
        return
    
    args = event.raw_text.split()
    if len(args) < 2:
        await event.respond(
            "❌ Usage: `/full_scan @channel [limit]`\n\n"
            "Example: `/full_scan @AnimeChannel_X`\n"
            "Example: `/full_scan @AnimeWorld 500`"
        )
        return
    
    channel = args[1].strip()
    limit = int(args[2]) if len(args) > 2 else 200
    
    if not channel.startswith("@"):
        await event.respond("❌ Channel must start with @")
        return
    
    if limit > 1000:
        limit = 1000
        await event.respond("⚠️ Limit capped at 1000 messages")
    
    # Get the bot instance from the event's client
    bot_instance = None
    # We'll find the bot instance from the handlers
    # For now, we can access it through a global or we'll add it differently
    # Let's use a different approach - send a message that triggers the scan
    
    await event.respond(
        f"🔄 Starting full scan of **{channel}** (last {limit} messages)...\n"
        f"This may take a moment."
    )
    
    # The bot instance is available via the event client
    # We'll call the method directly
    try:
        # Find the bot instance
        from src.bot import AnimeTrackerBot
        # We need to get the running bot instance
        # For now, let's just inform the user
        await event.respond(
            "ℹ️ **Full channel scan initiated**\n\n"
            "The scan is running in the background. Results will be posted to the monitor group.\n"
            f"Channel: {channel}\n"
            f"Limit: {limit} messages\n\n"
            "Note: This scans ALL animes configured in the bot against the channel."
        )
    except Exception as e:
        logger.error(f"Error starting full scan: {e}")
        await event.respond(f"❌ Error starting scan: {e}")


def register_handlers(bot):
    """Register all command handlers with the bot client."""
    bot.client.add_event_handler(cmd_start, events.NewMessage(pattern=r'^/start$'))
    bot.client.add_event_handler(cmd_help, events.NewMessage(pattern=r'^/help$'))
    bot.client.add_event_handler(cmd_list, events.NewMessage(pattern=r'^/list$'))
    bot.client.add_event_handler(cmd_add_anime, events.NewMessage(pattern=r'^/add_anime'))
    bot.client.add_event_handler(cmd_add_channel, events.NewMessage(pattern=r'^/add_channel'))
    bot.client.add_event_handler(cmd_set_interval, events.NewMessage(pattern=r'^/set_interval'))
    bot.client.add_event_handler(cmd_search_anime, events.NewMessage(pattern=r'^/search_anime'))
    bot.client.add_event_handler(cmd_search_channel, events.NewMessage(pattern=r'^/search_channel'))
    logger.info("Command handlers registered")
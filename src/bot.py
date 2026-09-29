#!/usr/bin/env python3
"""
Main Anime Tracker Bot

This is the main entry point for the bot. It runs the scheduled channel scanner
that monitors Telegram channels for new anime episodes and posts them to the
monitor group forum.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.database import (
    init_db, 
    get_active_animes,
    is_episode_seen,
    record_episode,
    get_or_create_topic,
    sync_animes_to_db,
    search_messages_in_channel,
    search_anime_by_title,
)
from src.anime_loader import load_animes_config, get_anime_dicts
from src.parser import match_aliases, parse_episode_number, build_anime_link
from src.commands import register_handlers, is_admin
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, ChannelPrivateError, UserNotParticipantError
from telethon.tl.types import Channel, Chat


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AnimeTrackerBot:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self.running = False
        self.scan_task = None
        
    async def initialize(self):
        """Initialize database and Telethon client."""
        # Initialize database
        await init_db(str(self.settings.db_path))
        logger.info(f"Database initialized at {self.settings.db_path}")
        
        # Sync animes from config
        config = load_animes_config("config/animes.json")
        anime_dicts = get_anime_dicts(config)
        stats = await sync_animes_to_db(str(self.settings.db_path), anime_dicts)
        logger.info(f"Synced animes: {stats}")
        
        # Initialize Telethon client
        self.client = TelegramClient(
            str(self.settings.session_path),
            self.settings.API_ID,
            self.settings.API_HASH
        )
        
        await self.client.start()
        me = await self.client.get_me()
        logger.info(f"Logged in as {me.first_name} (@{me.username})")
        
        # Verify monitor group access
        try:
            self.monitor_entity = await self.client.get_entity(self.settings.MONITOR_GROUP)
            logger.info(f"Monitor group: {self.monitor_entity.title} (ID: {self.monitor_entity.id})")
        except Exception as e:
            logger.error(f"Cannot access monitor group '{self.settings.MONITOR_GROUP}': {e}")
            raise
        
    async def global_search(self, query: str, limit_per_channel: int = 100) -> List[Dict[str, Any]]:
        """
        جستجوی عمومی در تمام کانال‌های تحت پایش برای یافتن یک انیمه.
        این متد پیام‌های کانال‌ها را مستقیماً جستجو می‌کند (نه فقط جدول episodes را)،
        بنابراین انیمه‌های تمام‌شده یا در حال پخشی که هنوز اسکن نشده‌اند را هم پیدا می‌کند.
        """
        # لیست یکتای تمام کانال‌های فعال
        animes = await get_active_animes(str(self.settings.db_path))
        channels: List[str] = []
        for anime in animes:
            for ch in (anime.channels or []):
                if ch not in channels:
                    channels.append(ch)

        # کانال‌های نامعتبر را فیلتر کن
        valid_channels: List[Any] = []
        for channel_name in channels:
            try:
                entity = await self.client.get_entity(channel_name)
                valid_channels.append((channel_name, entity))
            except Exception as e:
                logger.debug(f"Cannot access channel {channel_name} for global search: {e}")

        # جستجوی موازی با محدودیت همزمانی
        semaphore = asyncio.Semaphore(self.settings.MAX_CONCURRENT_SCANS)
        results: List[Dict[str, Any]] = []

        async def search_one(channel_name: str, entity: Any):
            async with semaphore:
                try:
                    async for message in self.client.iter_messages(entity, limit=limit_per_channel):
                        if not message.text:
                            continue
                        text = message.text
                        # تطابق با عنوان یا نام‌های مستعار هر انیمه
                        for anime in animes:
                            if not match_aliases(text, anime.aliases):
                                continue
                            parse_result = parse_episode_number(text)
                            results.append({
                                "anime_title": anime.title,
                                "anime_id": anime.id,
                                "channel": channel_name,
                                "message_id": message.id,
                                "episode_number": parse_result.episode_number if parse_result else None,
                                "text": text[:300],
                                "link": build_anime_link(channel_name, message.id),
                                "date": message.date.isoformat() if message.date else None,
                            })
                except Exception as e:
                    logger.debug(f"Error searching {channel_name}: {e}")

        tasks = [search_one(name, entity) for name, entity in valid_channels]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # مرتب‌سازی بر اساس تاریخ (جدیدترین اول)
        results.sort(key=lambda r: (r.get("date") or "", r.get("anime_title", "")), reverse=True)
        return results

    async def scan_channel(self, anime, channel_name: str):
        """Scan a single channel for new episodes of an anime."""
        logger.debug(f"Scanning {channel_name} for '{anime.title}'")
        
        try:
            entity = await self.client.get_entity(channel_name)
        except (ChannelPrivateError, UserNotParticipantError, ValueError) as e:
            logger.warning(f"Cannot access channel {channel_name}: {e}")
            return
        except Exception as e:
            logger.error(f"Error getting entity for {channel_name}: {e}")
            return
        
        # Get recent messages (last 50)
        try:
            messages = []
            async for message in self.client.iter_messages(entity, limit=50):
                messages.append(message)
        except Exception as e:
            logger.error(f"Error fetching messages from {channel_name}: {e}")
            return
        
        # Process messages in chronological order (oldest first)
        for message in reversed(messages):
            if not message.text:
                continue
                
            # Check if this message matches any alias
            matched_aliases = match_aliases(message.text, anime.aliases)
            if not matched_aliases:
                continue
                
            # Try to parse episode number
            parse_result = parse_episode_number(message.text)
            if not parse_result:
                logger.debug(f"Matched alias but no episode number in: {message.text[:100]}")
                continue
                
            episode_num = parse_result.episode_number
            
            # Check if already seen
            if await is_episode_seen(str(self.settings.db_path), anime.id, episode_num):
                logger.debug(f"Episode {episode_num} of '{anime.title}' already seen")
                continue
                
            # New episode found!
            logger.info(f"🎉 New episode: {anime.title} Ep {episode_num} in {channel_name}")
            
            # Record episode
            await record_episode(
                str(self.settings.db_path),
                anime.id,
                episode_num,
                message.id,
                channel_name.lstrip('@')
            )
            
            # Get or create topic
            topic_id = await get_or_create_topic(
                str(self.settings.db_path),
                anime.id,
                self.monitor_entity.id,
                0  # Will be created if needed
            )
            
            # If topic_id is 0, we need to create the topic
            if topic_id == 0:
                # Create forum topic
                try:
                    result = await self.client.send_message(
                        self.monitor_entity.id,
                        f"📺 {anime.title}",
                        reply_to=0  # This will be handled by the forum topic creation
                    )
                    # Actually create a forum topic - with fallback for older Telethon versions
                    try:
                        from telethon.tl.functions.channels import CreateForumTopicRequest
                        topic_result = await self.client(CreateForumTopicRequest(
                            channel=self.monitor_entity.id,
                            title=anime.title,
                            icon_color=0x6FB5E8  # Light blue
                        ))
                    except ImportError:
                        logger.warning(f"CreateForumTopicRequest not available, cannot create topic for {anime.title}")
                        continue
                    topic_id = topic_result.updates[0].id
                    
                    # Update database with new topic_id
                    from src.database import get_db_connection
                    conn = await get_db_connection(str(self.settings.db_path))
                    try:
                        await conn.execute(
                            "UPDATE topics SET topic_id = ? WHERE anime_id = ?;",
                            (topic_id, anime.id)
                        )
                        await conn.commit()
                    finally:
                        await conn.close()
                        
                except Exception as e:
                    logger.error(f"Failed to create topic for {anime.title}: {e}")
                    continue
            
            # Build message with link
            link = build_anime_link(channel_name, message.id)
            badge = "🆕 " if parse_result.confidence >= 0.9 else ""
            post_text = f"{badge}{anime.title} - Episode {episode_num}\n\n🔗 {link}"
            
            # Post to topic
            try:
                await self.client.send_message(
                    self.monitor_entity.id,
                    post_text,
                    reply_to=topic_id
                )
                logger.info(f"Posted to topic {topic_id}: {anime.title} Ep {episode_num}")
            except Exception as e:
                logger.error(f"Failed to post to topic {topic_id}: {e}")
    
    async def scan_all(self):
        """Scan all channels for all active animes in parallel with concurrency control."""
        logger.info("Starting scan cycle...")
        
        animes = await get_active_animes(str(self.settings.db_path))
        if not animes:
            logger.info("No active animes configured")
            return
        
        # Limit concurrent channel scans to avoid flood waits
        semaphore = asyncio.Semaphore(5)
        
        async def scan_with_limit(anime, channel):
            async with semaphore:
                try:
                    await self.scan_channel(anime, channel)
                except Exception as e:
                    logger.error(f"Error scanning {channel} for '{anime.title}': {e}")
                # Small delay between channels to avoid flood
                await asyncio.sleep(0.5)
        
        tasks = [
            scan_with_limit(anime, channel)
            for anime in animes
            for channel in anime.channels
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
                
        logger.info("Scan cycle complete")

    async def full_scan_channel(self, channel_name: str, limit: int = 200, animes_filter: Optional[List] = None):
        """
        Perform a deep scan of a channel (more than 50 recent messages).
        This searches through more messages to find episodes that might have been missed.
        
        Args:
            channel_name: Channel username (e.g., @AnimeChannel_X)
            limit: Maximum number of messages to scan (default 200, max 1000)
            animes_filter: Optional list of AnimeRow to limit search to specific animes
        """
        logger.info(f"Starting FULL scan of {channel_name} (limit: {limit})")
        
        try:
            entity = await self.client.get_entity(channel_name)
        except (ChannelPrivateError, UserNotParticipantError, ValueError) as e:
            logger.warning(f"Cannot access channel {channel_name}: {e}")
            return {"scanned": 0, "found": 0, "error": str(e)}
        except Exception as e:
            logger.error(f"Error getting entity for {channel_name}: {e}")
            return {"scanned": 0, "found": 0, "error": str(e)}
        
        # Get messages
        try:
            messages = []
            async for message in self.client.iter_messages(entity, limit=limit):
                messages.append(message)
        except Exception as e:
            logger.error(f"Error fetching messages from {channel_name}: {e}")
            return {"scanned": 0, "found": 0, "error": str(e)}
        
        logger.info(f"Fetched {len(messages)} messages from {channel_name}")
        
        # Determine which animes to scan for
        if animes_filter is None:
            animes_to_scan = await get_active_animes(str(self.settings.db_path))
        else:
            animes_to_scan = animes_filter
        
        found_count = 0
        scanned_count = 0
        
        # Process messages in chronological order (oldest first)
        for message in reversed(messages):
            if not message.text:
                continue
            
            scanned_count += 1
            
            # Check against all animes
            for anime in animes_to_scan:
                matched_aliases = match_aliases(message.text, anime.aliases)
                if not matched_aliases:
                    continue
                
                parse_result = parse_episode_number(message.text)
                if not parse_result:
                    continue
                
                episode_num = parse_result.episode_number
                
                # Check if already seen
                if await is_episode_seen(str(self.settings.db_path), anime.id, episode_num):
                    continue
                
                # New episode found!
                logger.info(f"🎉 Full scan found: {anime.title} Ep {episode_num} in {channel_name}")
                
                # Record episode
                await record_episode(
                    str(self.settings.db_path),
                    anime.id,
                    episode_num,
                    message.id,
                    channel_name.lstrip('@')
                )
                
                # Get or create topic
                topic_id = await get_or_create_topic(
                    str(self.settings.db_path),
                    anime.id,
                    self.monitor_entity.id,
                    0
                )
                
                if topic_id == 0:
                    try:
                        # Try to use CreateForumTopicRequest if available (newer Telethon versions)
                        from telethon.tl.functions.channels import CreateForumTopicRequest
                        topic_result = await self.client(CreateForumTopicRequest(
                            channel=self.monitor_entity.id,
                            title=anime.title,
                            icon_color=0x6FB5E8
                        ))
                        topic_id = topic_result.updates[0].id
                    except ImportError:
                        # Fallback: CreateForumTopicRequest not available in this Telethon version
                        # Use CreateChannelRequest with forum=True or just log and continue
                        logger.warning(f"CreateForumTopicRequest not available, cannot create topic for {anime.title}")
                        continue
                    except Exception as e:
                        logger.error(f"Failed to create topic for {anime.title}: {e}")
                        continue
                    
                    from src.database import get_db_connection
                    conn = await get_db_connection(str(self.settings.db_path))
                    try:
                        await conn.execute(
                            "UPDATE topics SET topic_id = ? WHERE anime_id = ?;",
                            (topic_id, anime.id)
                        )
                        await conn.commit()
                    finally:
                        await conn.close()
                
                # Build and post message
                link = build_anime_link(channel_name, message.id)
                badge = "🆕 " if parse_result.confidence >= 0.9 else ""
                post_text = f"{badge}{anime.title} - Episode {episode_num}\n\n🔗 {link}"
                
                try:
                    await self.client.send_message(
                        self.monitor_entity.id,
                        post_text,
                        reply_to=topic_id
                    )
                    logger.info(f"Posted to topic {topic_id}: {anime.title} Ep {episode_num}")
                    found_count += 1
                except Exception as e:
                    logger.error(f"Failed to post to topic {topic_id}: {e}")
        
        logger.info(f"Full scan complete: {channel_name} - Scanned: {scanned_count}, Found: {found_count}")
        return {"scanned": scanned_count, "found": found_count}
    
    async def run_scanner(self):
        """Main scanner loop."""
        self.running = True
        logger.info(f"Scanner started, interval: {self.settings.CHECK_INTERVAL}s")
        
        while self.running:
            try:
                await self.scan_all()
            except FloodWaitError as e:
                logger.warning(f"FloodWait: sleeping for {e.seconds}s")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Error in scan cycle: {e}")
            
            # Wait for next interval
            try:
                await asyncio.sleep(self.settings.CHECK_INTERVAL)
            except asyncio.CancelledError:
                break
    
    async def start(self):
        """Start the bot."""
        await self.initialize()
        
        # Register command handlers
        register_handlers(self)
        
        # Register global search command handler
        @self.client.on(events.NewMessage(pattern=r'^/search'))
        async def handle_global_search(event):
            """جستجوی عمومی در تمام کانال‌های تحت پایش."""
            if not is_admin(event.sender_id):
                await event.respond("❌ Unauthorized")
                return

            args = event.raw_text.split(maxsplit=1)
            if len(args) < 2 or not args[1].strip():
                await event.respond(
                    "❌ Usage: `/search <anime title>`\n\n"
                    "Example: `/search Jujutsu Kaisen`\n"
                    "Example: `/search جوجوتسو`"
                )
                return

            query = args[1].strip()
            await event.respond(f"🔍 در حال جستجوی **{query}** در تمام کانال‌های تحت پایش...")

            try:
                results = await self.global_search(query)
                if not results:
                    await event.respond(
                        f"🔍 هیچ نتیجه‌ای برای **{query}** یافت نشد.\n"
                        f"ممکن است این انیمه هنوز به لیست اضافه نشده باشد. "
                        f"از `/add_anime` برای افزودن آن استفاده کنید."
                    )
                    return

                # حداکثر ۲۰ نتیجه
                top = results[:20]
                lines = [f"🔍 **نتایج جستجو برای '{query}'** — {len(results)} مورد یافت شد\n"]
                for i, r in enumerate(top, 1):
                    ep_str = f" - Episode {r['episode_number']}" if r.get("episode_number") else ""
                    lines.append(
                        f"**{i}. {r['anime_title']}**{ep_str}\n"
                        f"   📡 {r['channel']}\n"
                        f"   🔗 {r['link']}"
                    )
                if len(results) > len(top):
                    lines.append(f"\n... و {len(results) - len(top)} نتیجه دیگر")

                await event.respond("\n".join(lines))
            except Exception as e:
                logger.error(f"Error in global search: {e}")
                await event.respond(f"❌ جستجو ناموفق بود: {e}")

        # Register full_scan command handler
        @self.client.on(events.NewMessage(pattern=r'^/full_scan'))
        async def handle_full_scan(event):
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
            
            await event.respond(
                f"🔄 Starting full scan of **{channel}** (last {limit} messages)...\n"
                f"This may take a moment."
            )
            
            try:
                result = await self.full_scan_channel(channel, limit)
                await event.respond(
                    f"✅ **Full scan complete!**\n\n"
                    f"📺 Channel: {channel}\n"
                    f"🔍 Messages scanned: {result['scanned']}\n"
                    f"🎉 New episodes found: {result['found']}"
                    + (f"\n⚠️ Error: {result['error']}" if result.get('error') else "")
                )
            except Exception as e:
                logger.error(f"Error in full scan: {e}")
                await event.respond(f"❌ Scan failed: {e}")
        
        self.scan_task = asyncio.create_task(self.run_scanner())
        logger.info("Bot started!")
        
        # Wait for scan task
        try:
            await self.scan_task
        except asyncio.CancelledError:
            pass
    
    async def stop(self):
        """Stop the bot."""
        logger.info("Stopping bot...")
        self.running = False
        if self.scan_task:
            self.scan_task.cancel()
            try:
                await self.scan_task
            except asyncio.CancelledError:
                pass
        if self.client:
            await self.client.disconnect()
        logger.info("Bot stopped")


async def main():
    bot = AnimeTrackerBot()
    
    # Setup signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.stop()))
    
    try:
        await bot.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
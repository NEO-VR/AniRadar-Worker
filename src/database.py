import aiosqlite
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class AnimeRow:
    id: int
    title: str
    is_active: bool
    created_at: str
    aliases: List[str]
    channels: List[str]


@dataclass
class EpisodeRow:
    id: int
    anime_id: int
    episode_number: float
    message_id: int
    channel: str
    created_at: str


@dataclass
class TopicRow:
    id: int
    anime_id: int
    group_id: int
    topic_id: int
    created_at: str


async def get_db_connection(db_path: str) -> aiosqlite.Connection:
    """
    Establishes and returns an async connection to the SQLite database.
    Enforces foreign key constraints.
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    # جلوگیری از خطای "database is locked" هنگام دسترسی همزمان worker و API
    await conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


async def init_db(db_path: str) -> None:
    """
    Initializes the database schema by creating the required tables if they don't exist.
    Uses soft-delete pattern for animes (is_active column) to preserve episode history.
    Enables WAL mode for better concurrency.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = await aiosqlite.connect(db_path)
    try:
        conn.row_factory = aiosqlite.Row
        # Enable WAL mode for better concurrent access
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA foreign_keys = ON;")
        # Create animes table with is_active for soft delete
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS animes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT UNIQUE NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create aliases table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                UNIQUE(anime_id, alias),
                FOREIGN KEY (anime_id) REFERENCES animes (id) ON DELETE CASCADE
            );
        """)

        # Create channels table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER NOT NULL,
                channel_name TEXT NOT NULL,
                UNIQUE(anime_id, channel_name),
                FOREIGN KEY (anime_id) REFERENCES animes (id) ON DELETE CASCADE
            );
        """)

        # Create episodes table - NO CASCADE DELETE to preserve history
        # If anime is deactivated, episodes remain for deduplication
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER NOT NULL,
                episode_number REAL NOT NULL,
                message_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(anime_id, episode_number),
                FOREIGN KEY (anime_id) REFERENCES animes (id) ON DELETE RESTRICT
            );
        """)

        # Create topics table - NO CASCADE DELETE to preserve topic mapping
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                anime_id INTEGER UNIQUE NOT NULL,
                group_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (anime_id) REFERENCES animes (id) ON DELETE RESTRICT
            );
        """)

        # Migration: add is_active column if not exists (for existing databases)
        try:
            await conn.execute("ALTER TABLE animes ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1;")
        except aiosqlite.OperationalError:
            # Column already exists
            pass

        await conn.commit()
    finally:
        await conn.close()


async def sync_animes_to_db(db_path: str, animes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Synchronizes the list of validated anime dicts from the JSON config with the SQLite database.
    Uses soft delete: animes not in config are marked is_active=0 instead of being deleted.
    This preserves episode history and topic mappings.
    
    Returns:
        Dict with stats: {'added': int, 'updated': int, 'deactivated': int, 'reactivated': int}
    """
    conn = await aiosqlite.connect(db_path)
    try:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON;")
        stats = {"added": 0, "updated": 0, "deactivated": 0, "reactivated": 0}
        
        # 1. Get titles in new config
        config_titles = {anime["title"] for anime in animes}
        
        # 2. Get existing titles from DB
        cursor = await conn.execute("SELECT title, is_active FROM animes;")
        existing = {row["title"]: row["is_active"] for row in await cursor.fetchall()}
        
        # 3. Deactivate animes not in config (soft delete)
        to_deactivate = [title for title, active in existing.items() if title not in config_titles and active == 1]
        if to_deactivate:
            placeholders = ",".join("?" for _ in to_deactivate)
            await conn.execute(
                f"UPDATE animes SET is_active = 0 WHERE title IN ({placeholders});",
                to_deactivate
            )
            stats["deactivated"] = len(to_deactivate)
        
        # 4. Reactivate animes that are back in config
        to_reactivate = [title for title, active in existing.items() if title in config_titles and active == 0]
        if to_reactivate:
            placeholders = ",".join("?" for _ in to_reactivate)
            await conn.execute(
                f"UPDATE animes SET is_active = 1 WHERE title IN ({placeholders});",
                to_reactivate
            )
            stats["reactivated"] = len(to_reactivate)
        
        # 5. Insert new animes and sync aliases/channels
        for anime in animes:
            title = anime["title"]
            aliases = anime["aliases"]
            channels = anime["channels"]
            
            # Insert or ignore anime
            cursor = await conn.execute(
                "INSERT OR IGNORE INTO animes (title, is_active) VALUES (?, 1);",
                (title,)
            )
            if cursor.rowcount > 0:
                stats["added"] += 1
            else:
                # Check if was deactivated and now reactivated
                row = await (await conn.execute("SELECT is_active FROM animes WHERE title = ?;", (title,))).fetchone()
                if row and row["is_active"] == 0:
                    stats["reactivated"] += 1
                else:
                    stats["updated"] += 1
            
            # Ensure is_active = 1 for all animes in config
            await conn.execute(
                "UPDATE animes SET is_active = 1 WHERE title = ?;",
                (title,)
            )
            
            # Retrieve its ID
            row = await (await conn.execute("SELECT id FROM animes WHERE title = ?;", (title,))).fetchone()
            anime_id = row["id"]
            
            # Sync Aliases: delete obsolete, insert new
            if aliases:
                alias_placeholders = ",".join("?" for _ in aliases)
                await conn.execute(
                    f"DELETE FROM aliases WHERE anime_id = ? AND alias NOT IN ({alias_placeholders});",
                    [anime_id] + aliases
                )
                for alias in aliases:
                    await conn.execute(
                        "INSERT OR IGNORE INTO aliases (anime_id, alias) VALUES (?, ?);",
                        (anime_id, alias)
                    )
            else:
                await conn.execute("DELETE FROM aliases WHERE anime_id = ?;", (anime_id,))
            
            # Sync Channels: delete obsolete, insert new
            if channels:
                channel_placeholders = ",".join("?" for _ in channels)
                await conn.execute(
                    f"DELETE FROM channels WHERE anime_id = ? AND channel_name NOT IN ({channel_placeholders});",
                    [anime_id] + channels
                )
                for channel in channels:
                    await conn.execute(
                        "INSERT OR IGNORE INTO channels (anime_id, channel_name) VALUES (?, ?);",
                        (anime_id, channel)
                    )
            else:
                await conn.execute("DELETE FROM channels WHERE anime_id = ?;", (anime_id,))
        
        await conn.commit()
    finally:
        await conn.close()
    
    return stats


async def get_active_animes(db_path: str) -> List[AnimeRow]:
    """Get all active animes with their aliases and channels."""
    conn = await get_db_connection(db_path)
    try:
        cursor = await conn.execute("""
            SELECT a.id, a.title, a.is_active, a.created_at,
                   GROUP_CONCAT(DISTINCT al.alias) as aliases,
                   GROUP_CONCAT(DISTINCT c.channel_name) as channels
            FROM animes a
            LEFT JOIN aliases al ON a.id = al.anime_id
            LEFT JOIN channels c ON a.id = c.anime_id
            WHERE a.is_active = 1
            GROUP BY a.id, a.title, a.is_active, a.created_at
        """)
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            result.append(AnimeRow(
                id=row["id"],
                title=row["title"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                aliases=row["aliases"].split(",") if row["aliases"] else [],
                channels=row["channels"].split(",") if row["channels"] else []
            ))
        return result
    finally:
        await conn.close()


async def is_episode_seen(db_path: str, anime_id: int, episode_number: float) -> bool:
    """Check if an episode has already been recorded."""
    conn = await get_db_connection(db_path)
    try:
        cursor = await conn.execute(
            "SELECT 1 FROM episodes WHERE anime_id = ? AND episode_number = ?;",
            (anime_id, episode_number)
        )
        return await cursor.fetchone() is not None
    finally:
        await conn.close()


async def record_episode(
    db_path: str, 
    anime_id: int, 
    episode_number: float, 
    message_id: int, 
    channel: str
) -> bool:
    """
    Record a new episode. Returns True if inserted, False if duplicate.
    """
    conn = await get_db_connection(db_path)
    try:
        cursor = await conn.execute(
            """INSERT OR IGNORE INTO episodes (anime_id, episode_number, message_id, channel) 
               VALUES (?, ?, ?, ?);""",
            (anime_id, episode_number, message_id, channel)
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def get_or_create_topic(
    db_path: str, 
    anime_id: int, 
    group_id: int, 
    topic_id: int
) -> int:
    """
    Get existing topic_id for anime or create new mapping.
    Returns the topic_id.
    """
    conn = await get_db_connection(db_path)
    try:
        # Try to get existing
        cursor = await conn.execute(
            "SELECT topic_id FROM topics WHERE anime_id = ?;",
            (anime_id,)
        )
        row = await cursor.fetchone()
        if row:
            return row["topic_id"]
        
        # Create new mapping
        await conn.execute(
            "INSERT INTO topics (anime_id, group_id, topic_id) VALUES (?, ?, ?);",
            (anime_id, group_id, topic_id)
        )
        await conn.commit()
        return topic_id
    finally:
        await conn.close()


async def get_topic(db_path: str, anime_id: int) -> Optional[TopicRow]:
    """Get topic mapping for an anime."""
    conn = await get_db_connection(db_path)
    try:
        cursor = await conn.execute(
            "SELECT * FROM topics WHERE anime_id = ?;",
            (anime_id,)
        )
        row = await cursor.fetchone()
        if row:
            return TopicRow(
                id=row["id"],
                anime_id=row["anime_id"],
                group_id=row["group_id"],
                topic_id=row["topic_id"],
                created_at=row["created_at"]
            )
        return None
    finally:
        await conn.close()


async def search_messages_in_channel(db_path: str, channel: str, query: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    جستجوی پیام‌ها در یک کانال مشخص بر اساس عبارت جستجو.
    این تابع جدول episodes را با animes ترکیب می‌کند و عبارت جستجو را
    در عنوان انیمه یا نام‌های مستعار آن تطابق می‌دهد.
    """
    conn = await get_db_connection(db_path)
    try:
        # الگوی جستجو با LIKE
        search_pattern = f"%{query}%"
        cursor = await conn.execute("""
            SELECT e.*, a.title as anime_title
            FROM episodes e
            JOIN animes a ON e.anime_id = a.id
            WHERE e.channel = ?
            AND (a.title LIKE ? OR EXISTS (
                SELECT 1 FROM aliases al WHERE al.anime_id = a.id AND al.alias LIKE ?
            ))
            ORDER BY e.episode_number DESC
            LIMIT ?
        """, (channel.lstrip('@'), search_pattern, search_pattern, limit))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await conn.close()


async def search_anime_by_title(db_path: str, query: str, limit: int = 50) -> List[AnimeRow]:
    """
    Search for anime by title or alias (fuzzy match).
    Returns active animes that match the query.
    """
    conn = await get_db_connection(db_path)
    try:
        search_pattern = f"%{query}%"
        cursor = await conn.execute("""
            SELECT a.id, a.title, a.is_active, a.created_at,
                   GROUP_CONCAT(DISTINCT al.alias) as aliases,
                   GROUP_CONCAT(DISTINCT c.channel_name) as channels
            FROM animes a
            LEFT JOIN aliases al ON a.id = al.anime_id
            LEFT JOIN channels c ON a.id = c.anime_id
            WHERE a.is_active = 1
            AND (a.title LIKE ? OR al.alias LIKE ?)
            GROUP BY a.id, a.title, a.is_active, a.created_at
            LIMIT ?
        """, (search_pattern, search_pattern, limit))
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            result.append(AnimeRow(
                id=row["id"],
                title=row["title"],
                is_active=bool(row["is_active"]),
                created_at=row["created_at"],
                aliases=row["aliases"].split(",") if row["aliases"] else [],
                channels=row["channels"].split(",") if row["channels"] else []
            ))
        return result
    finally:
        await conn.close()
import os
import tempfile
import unittest
import json
import asyncio
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError

# Configure source path imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Settings, get_settings
from src.database import (
    init_db, 
    get_db_connection, 
    sync_animes_to_db,
    get_active_animes,
    is_episode_seen,
    record_episode,
    get_or_create_topic,
    get_topic,
    AnimeRow,
    EpisodeRow,
    TopicRow
)
from src.anime_loader import load_animes_config, AnimesConfig, AnimeConfig, get_anime_dicts


class TestConfig(unittest.TestCase):
    @patch.dict(os.environ, {
        "API_ID": "987654", 
        "API_HASH": "test_hash_xyz", 
        "MONITOR_GROUP": "Test Group",
        "CHECK_INTERVAL": "600",
        "MAX_CONCURRENT_SCANS": "5"
    })
    def test_config_loading_success(self):
        cfg = Settings()
        self.assertEqual(cfg.API_ID, 987654)
        self.assertEqual(cfg.API_HASH, "test_hash_xyz")
        self.assertEqual(cfg.MONITOR_GROUP, "Test Group")
        self.assertEqual(cfg.CHECK_INTERVAL, 600)
        self.assertEqual(cfg.MAX_CONCURRENT_SCANS, 5)
        self.assertEqual(cfg.SESSION_NAME, "anime_tracker")

    @patch.dict(os.environ, {"API_ID": "abc", "API_HASH": "test_hash_xyz"})
    def test_config_invalid_api_id(self):
        with self.assertRaises(ValidationError) as ctx:
            Settings()
        self.assertIn("API_ID", str(ctx.exception))

    @patch.dict(os.environ, {}, clear=True)
    def test_config_missing_api_id(self):
        with patch.dict("src.config.Settings.model_config", {"env_file": None, "env_file_encoding": None}):
            with self.assertRaises(ValidationError) as ctx:
                Settings(_env_file=None, _env_file_encoding=None)
            self.assertIn("API_ID", str(ctx.exception))


class TestDatabase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name

    async def asyncTearDown(self):
        if Path(self.db_path).exists():
            os.remove(self.db_path)

    async def test_db_initialization(self):
        await init_db(self.db_path)
        
        # Verify tables exist
        conn = await get_db_connection(self.db_path)
        try:
            cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row["name"] for row in await cursor.fetchall()}
            
            expected_tables = {"animes", "aliases", "channels", "episodes", "topics"}
            self.assertTrue(expected_tables.issubset(tables))
            
            # Check animes table has is_active column
            cursor = await conn.execute("PRAGMA table_info(animes);")
            columns = {row["name"] for row in await cursor.fetchall()}
            self.assertIn("is_active", columns)
        finally:
            await conn.close()

    async def test_sync_animes_to_db_soft_delete(self):
        await init_db(self.db_path)
        
        test_animes = [
            {
                "title": "Jujutsu Kaisen",
                "aliases": ["jjk", "jujutsu kaisen"],
                "channels": ["@jjk_channel"]
            },
            {
                "title": "Demon Slayer",
                "aliases": ["ds", "kimetsu"],
                "channels": ["@demonslayer_channel", "@anime_hub"]
            }
        ]

        # 1. Sync first time
        stats = await sync_animes_to_db(self.db_path, test_animes)
        self.assertEqual(stats["added"], 2)
        self.assertEqual(stats["deactivated"], 0)
        
        conn = await get_db_connection(self.db_path)
        try:
            # Check animes
            cursor = await conn.execute("SELECT * FROM animes ORDER BY title;")
            animes_rows = await cursor.fetchall()
            self.assertEqual(len(animes_rows), 2)
            self.assertTrue(all(row["is_active"] == 1 for row in animes_rows))
        finally:
            await conn.close()

        # 2. Sync with modification (remove Demon Slayer from config - should be deactivated, not deleted)
        modified_animes = [
            {
                "title": "Jujutsu Kaisen",
                "aliases": ["jjk", "jujutsu kaisen", "jjk s2"],
                "channels": ["@jjk_channel_new"]
            }
        ]

        stats = await sync_animes_to_db(self.db_path, modified_animes)
        self.assertEqual(stats["deactivated"], 1)  # Demon Slayer deactivated
        self.assertEqual(stats["updated"], 1)       # JJK updated
        
        conn = await get_db_connection(self.db_path)
        try:
            # Demon Slayer should still exist but be inactive
            cursor = await conn.execute("SELECT title, is_active FROM animes ORDER BY title;")
            animes_rows = await cursor.fetchall()
            self.assertEqual(len(animes_rows), 2)
            
            # Find Demon Slayer
            ds = next(row for row in animes_rows if row["title"] == "Demon Slayer")
            self.assertEqual(ds["is_active"], 0)  # Soft deleted!
            
            # JJK should be active
            jjk = next(row for row in animes_rows if row["title"] == "Jujutsu Kaisen")
            self.assertEqual(jjk["is_active"], 1)
        finally:
            await conn.close()

    async def test_get_active_animes(self):
        await init_db(self.db_path)
        
        test_animes = [
            {
                "title": "Jujutsu Kaisen",
                "aliases": ["jjk", "jujutsu kaisen"],
                "channels": ["@jjk_channel"]
            },
            {
                "title": "Demon Slayer",
                "aliases": ["ds", "kimetsu"],
                "channels": ["@demonslayer_channel"]
            }
        ]
        
        await sync_animes_to_db(self.db_path, test_animes)
        
        active = await get_active_animes(self.db_path)
        self.assertEqual(len(active), 2)
        self.assertTrue(all(a.is_active for a in active))
        self.assertEqual(set(a.title for a in active), {"Jujutsu Kaisen", "Demon Slayer"})
        
        # Check aliases and channels loaded
        jjk = next(a for a in active if a.title == "Jujutsu Kaisen")
        self.assertEqual(set(jjk.aliases), {"jjk", "jujutsu kaisen"})
        self.assertEqual(set(jjk.channels), {"@jjk_channel"})

    async def test_episode_deduplication(self):
        await init_db(self.db_path)
        
        test_animes = [
            {"title": "Test Anime", "aliases": ["test"], "channels": ["@test"]}
        ]
        await sync_animes_to_db(self.db_path, test_animes)
        
        # Get anime_id
        conn = await get_db_connection(self.db_path)
        try:
            cursor = await conn.execute("SELECT id FROM animes WHERE title = ?;", ("Test Anime",))
            row = await cursor.fetchone()
            anime_id = row["id"]
        finally:
            await conn.close()
        
        # First record - should succeed
        result = await record_episode(self.db_path, anime_id, 1.0, 12345, "@test")
        self.assertTrue(result)
        
        # Duplicate - should fail
        result = await record_episode(self.db_path, anime_id, 1.0, 12346, "@test")
        self.assertFalse(result)
        
        # Different episode - should succeed
        result = await record_episode(self.db_path, anime_id, 2.0, 12347, "@test")
        self.assertTrue(result)
        
        # Check seen
        seen = await is_episode_seen(self.db_path, anime_id, 1.0)
        self.assertTrue(seen)
        
        not_seen = await is_episode_seen(self.db_path, anime_id, 3.0)
        self.assertFalse(not_seen)

    async def test_topic_management(self):
        await init_db(self.db_path)
        
        test_animes = [
            {"title": "Test Anime", "aliases": ["test"], "channels": ["@test"]}
        ]
        await sync_animes_to_db(self.db_path, test_animes)
        
        conn = await get_db_connection(self.db_path)
        try:
            cursor = await conn.execute("SELECT id FROM animes WHERE title = ?;", ("Test Anime",))
            row = await cursor.fetchone()
            anime_id = row["id"]
        finally:
            await conn.close()
        
        # Create topic
        topic_id = await get_or_create_topic(self.db_path, anime_id, -1001234567890, 123)
        self.assertEqual(topic_id, 123)
        
        # Get existing topic
        topic_id2 = await get_or_create_topic(self.db_path, anime_id, -1001234567890, 456)
        self.assertEqual(topic_id2, 123)  # Should return existing
        
        # Verify topic row
        topic = await get_topic(self.db_path, anime_id)
        self.assertIsNotNone(topic)
        self.assertEqual(topic.anime_id, anime_id)
        self.assertEqual(topic.topic_id, 123)


class TestAnimeLoader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "animes.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_load_non_existent_file_creates_default(self):
        self.assertFalse(self.config_path.exists())
        config = load_animes_config(str(self.config_path))
        self.assertIsInstance(config, AnimesConfig)
        self.assertEqual(config.animes, [])
        self.assertTrue(self.config_path.exists())
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, {"animes": []})

    def test_load_valid_config(self):
        test_data = {
            "animes": [
                {
                    "title": "Jujutsu Kaisen",
                    "aliases": ["jjk", "jujutsu kaisen"],
                    "channels": ["@jjk_channel"]
                }
            ]
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)
        
        config = load_animes_config(str(self.config_path))
        self.assertEqual(len(config.animes), 1)
        self.assertEqual(config.animes[0].title, "Jujutsu Kaisen")
        self.assertEqual(config.animes[0].aliases, ["jjk", "jujutsu kaisen"])
        self.assertEqual(config.animes[0].channels, ["@jjk_channel"])

    def test_validate_strips_whitespace(self):
        item = {
            "title": "  One Piece  ",
            "aliases": ["  op  ", " one piece "],
            "channels": ["  @op_channel  "]
        }
        # Test through Pydantic model
        anime = AnimeConfig(**item)
        self.assertEqual(anime.title, "One Piece")
        self.assertEqual(anime.aliases, ["op", "one piece"])
        self.assertEqual(anime.channels, ["@op_channel"])

    def test_validate_invalid_items(self):
        # Missing title
        with self.assertRaises(ValidationError):
            AnimeConfig(aliases=["a"], channels=["c"])

        # Empty title (length < 1 after strip)
        with self.assertRaises(ValueError):
            AnimeConfig(title="   ", aliases=["a"], channels=["c"])

        # Missing aliases
        with self.assertRaises(ValidationError):
            AnimeConfig(title="Op", channels=["c"])

        # Missing channels
        with self.assertRaises(ValidationError):
            AnimeConfig(title="Op", aliases=["a"])

    def test_get_anime_dicts(self):
        config = AnimesConfig(animes=[
            AnimeConfig(title="Test", aliases=["t"], channels=["@c"])
        ])
        dicts = get_anime_dicts(config)
        self.assertEqual(len(dicts), 1)
        self.assertEqual(dicts[0]["title"], "Test")
        self.assertEqual(dicts[0]["aliases"], ["t"])
        self.assertEqual(dicts[0]["channels"], ["@c"])


if __name__ == "__main__":
    unittest.main()
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import (
    normalize_text,
    normalize_alias,
    match_aliases,
    parse_episode_number,
    parse_all_episodes,
    build_anime_link,
    extract_channel_name,
    ParseResult
)


class TestNormalization(unittest.TestCase):
    def test_normalize_text_basic(self):
        self.assertEqual(normalize_text("Hello World"), "hello world")
        self.assertEqual(normalize_text("HELLO WORLD"), "hello world")
    
    def test_normalize_text_punctuation(self):
        self.assertEqual(normalize_text("Hello, World!"), "hello world")
        self.assertEqual(normalize_text("Jujutsu-Kaisen"), "jujutsu kaisen")
        self.assertEqual(normalize_text("Jujutsu Kaisen (TV)"), "jujutsu kaisen tv")
    
    def test_normalize_text_cjk(self):
        self.assertEqual(normalize_text("第12話"), "第12話")
        self.assertEqual(normalize_text("鬼滅の刃"), "鬼滅の刃")
    
    def test_normalize_text_spaces(self):
        self.assertEqual(normalize_text("  Hello   World  "), "hello world")
        self.assertEqual(normalize_text("Hello\t\nWorld"), "hello world")
    
    def test_normalize_alias(self):
        self.assertEqual(normalize_alias("JJK"), "jjk")
        self.assertEqual(normalize_alias("  JuJutsu  "), "jujutsu")


class TestAliasMatching(unittest.TestCase):
    def test_match_aliases_basic(self):
        text = "New Jujutsu Kaisen episode released and JJK is great"
        aliases = ["jjk", "jujutsu kaisen", "jujutsu"]
        matched = match_aliases(text, aliases)
        self.assertEqual(set(matched), {"jjk", "jujutsu kaisen", "jujutsu"})
    
    def test_match_aliases_case_insensitive(self):
        text = "NEW JJK EPISODE"
        aliases = ["jjk"]
        matched = match_aliases(text, aliases)
        self.assertEqual(matched, ["jjk"])
    
    def test_match_aliases_punctuation(self):
        text = "Jujutsu-Kaisen_Ep12"
        aliases = ["jujutsu kaisen"]
        matched = match_aliases(text, aliases)
        self.assertEqual(matched, ["jujutsu kaisen"])
    
    def test_match_aliases_no_match(self):
        text = "One Piece episode"
        aliases = ["jjk", "jujutsu"]
        matched = match_aliases(text, aliases)
        self.assertEqual(matched, [])
    
    def test_match_aliases_empty(self):
        text = "Some text"
        aliases = []
        matched = match_aliases(text, aliases)
        self.assertEqual(matched, [])


class TestEpisodeParsing(unittest.TestCase):
    def test_parse_ep_format(self):
        result = parse_episode_number("Jujutsu Kaisen EP12 released")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 1.0)
    
    def test_parse_ep_with_space(self):
        result = parse_episode_number("EP 12 is out")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
    
    def test_parse_episode_word(self):
        result = parse_episode_number("Episode 24 is the finale")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 24.0)
        self.assertEqual(result.confidence, 1.0)
    
    def test_parse_bracketed(self):
        result = parse_episode_number("[12] Jujutsu Kaisen")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 0.9)
    
    def test_parse_season_episode(self):
        result = parse_episode_number("S01E12 - Great episode")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 1.0)
    
    def test_parse_season_episode_full(self):
        result = parse_episode_number("Season 1 Episode 5")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 5.0)
    
    def test_parse_hash(self):
        result = parse_episode_number("New episode #15")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 15.0)
        self.assertEqual(result.confidence, 0.8)
    
    def test_parse_cjk_japanese(self):
        result = parse_episode_number("第12話 公開")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 1.0)
    
    def test_parse_cjk_chinese(self):
        result = parse_episode_number("第12集 发布")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
    
    def test_parse_cjk_short(self):
        result = parse_episode_number("12話")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 0.9)
    
    def test_parse_korean(self):
        result = parse_episode_number("제12화 공개")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 1.0)
    
    def test_parse_korean_short(self):
        result = parse_episode_number("12화")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.0)
        self.assertEqual(result.confidence, 0.9)
    
    def test_parse_decimal_episode(self):
        result = parse_episode_number("EP12.5 special")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 12.5)
    
    def test_parse_no_match(self):
        result = parse_episode_number("Just some text without episode")
        self.assertIsNone(result)
    
    def test_parse_multiple_matches_picks_highest_confidence(self):
        # Has both bracketed (0.9) and EP format (1.0) - should pick EP
        result = parse_episode_number("[12] EP24")
        self.assertIsNotNone(result)
        self.assertEqual(result.episode_number, 24.0)
        self.assertEqual(result.confidence, 1.0)


class TestParseAllEpisodes(unittest.TestCase):
    def test_parse_all_multiple(self):
        results = parse_all_episodes("EP12 and EP13 released")
        self.assertEqual(len(results), 2)
        eps = {r.episode_number for r in results}
        self.assertEqual(eps, {12.0, 13.0})
    
    def test_parse_all_sorted_by_confidence(self):
        results = parse_all_episodes("[12] EP13")  # 0.9 vs 1.0
        self.assertEqual(results[0].episode_number, 13.0)  # Higher confidence first
        self.assertEqual(results[1].episode_number, 12.0)


class TestLinkBuilding(unittest.TestCase):
    def test_build_link_with_at(self):
        link = build_anime_link("@jjk_channel", 12345)
        self.assertEqual(link, "https://t.me/jjk_channel/12345")
    
    def test_build_link_without_at(self):
        link = build_anime_link("jjk_channel", 12345)
        self.assertEqual(link, "https://t.me/jjk_channel/12345")


class TestExtractChannel(unittest.TestCase):
    def test_extract_from_tme_link(self):
        text = "Check https://t.me/jjk_channel/12345 for new episode"
        channel = extract_channel_name(text)
        self.assertEqual(channel, "jjk_channel")
    
    def test_extract_from_mention(self):
        text = "Forwarded from @jjk_channel"
        channel = extract_channel_name(text)
        self.assertEqual(channel, "jjk_channel")
    
    def test_extract_none(self):
        text = "No channel here"
        channel = extract_channel_name(text)
        self.assertIsNone(channel)


if __name__ == "__main__":
    unittest.main()
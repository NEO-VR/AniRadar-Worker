#!/usr/bin/env python3
"""
Alias Matching and Episode Number Parser

Provides utilities for:
- Normalizing titles for matching (lowercase, strip punctuation/spaces)
- Matching aliases inside channel post text
- Parsing episode numbers from various formats:
  EP12, Episode 12, [12], S01E12, #12, 第12話, 第12集, 12話, etc.
"""

import re
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class ParseResult:
    """Result of episode parsing from a message."""
    episode_number: float
    matched_text: str
    confidence: float  # 0.0 to 1.0


# Regex patterns for episode numbers in various formats
EPISODE_PATTERNS = [
    # Standard formats
    (r'\bEP\s*(\d+(?:\.\d+)?)\b', 1.0),          # EP12, EP 12, EP12.5
    (r'\bEpisode\s*(\d+(?:\.\d+)?)\b', 1.0),     # Episode 12, Episode12
    (r'\bEpi\s*(\d+(?:\.\d+)?)\b', 0.9),         # Epi 12
    
    # Bracketed formats
    (r'\[\s*(\d+(?:\.\d+)?)\s*\]', 0.9),         # [12], [ 12 ]
    (r'\(\s*(\d+(?:\.\d+)?)\s*\)', 0.8),         # (12)
    (r'\{\s*(\d+(?:\.\d+)?)\s*\}', 0.7),         # {12}
    
    # Season/Episode formats
    (r'\bS(\d+)E(\d+(?:\.\d+)?)\b', 1.0),        # S01E12
    (r'\bSeason\s*(\d+)\s*Episode\s*(\d+(?:\.\d+)?)\b', 1.0),  # Season 1 Episode 12
    (r'\bS(\d+)\s*Ep?\s*(\d+(?:\.\d+)?)\b', 0.9), # S1 Ep12
    
    # Hash/number formats
    (r'#(\d+(?:\.\d+)?)\b', 0.8),                # #12
    (r'No\.?\s*(\d+(?:\.\d+)?)\b', 0.7),         # No. 12, No12
    (r'\bEp\.?\s*(\d+(?:\.\d+)?)\b', 0.9),       # Ep. 12, Ep12
    
    # CJK formats (Japanese/Chinese)
    (r'第\s*(\d+(?:\.\d+)?)\s*[話集]', 1.0),      # 第12話, 第12集
    (r'(\d+(?:\.\d+)?)\s*[話集]\b', 0.9),         # 12話, 12集
    (r'[第]\s*(\d+(?:\.\d+)?)\s*[话集]', 1.0),    # 第12话, 第12集 (Simplified)
    
    # Korean formats
    (r'제\s*(\d+(?:\.\d+)?)\s*화', 1.0),          # 제12화
    (r'(\d+(?:\.\d+)?)\s*화\b', 0.9),             # 12화
    
    # Plain number with context (lower confidence, used as fallback)
    (r'\b(\d+(?:\.\d+)?)\s*(?:ep|episode|e)\b', 0.6),  # 12 ep, 12 episode
]


def normalize_text(text: str) -> str:
    """
    Normalize text for matching: lowercase, remove punctuation and extra spaces.
    """
    # Convert to lowercase
    text = text.lower()
    # Replace punctuation with spaces
    text = re.sub(r'[^\w\s\u3000-\u303F\u4E00-\u9FFF\uAC00-\uD7AF]', ' ', text)
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def normalize_alias(alias: str) -> str:
    """
    Normalize an alias for matching: lowercase, strip.
    """
    return normalize_text(alias)


def match_aliases(text: str, aliases: List[str]) -> List[str]:
    """
    Find which aliases match in the given text.
    Returns list of matched aliases.
    """
    normalized_text = normalize_text(text)
    matched = []
    for alias in aliases:
        normalized_alias = normalize_alias(alias)
        if normalized_alias:
            # Check as whole word or substring
            # Use word boundaries for better matching
            pattern = r'(^|\s)' + re.escape(normalized_alias) + r'($|\s)'
            if re.search(pattern, ' ' + normalized_text + ' '):
                matched.append(alias)
            elif normalized_alias in normalized_text:
                # Fallback: substring match
                matched.append(alias)
    return matched


def parse_episode_number(text: str) -> Optional[ParseResult]:
    """
    Parse episode number from text using multiple regex patterns.
    Returns the best match (highest confidence) or None if no match.
    """
    best_match: Optional[ParseResult] = None
    
    for pattern, confidence in EPISODE_PATTERNS:
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        for match in matches:
            groups = match.groups()
            if len(groups) == 1:
                # Single capture group
                ep_num = float(groups[0])
            elif len(groups) == 2:
                # Season/episode format - use episode number only
                ep_num = float(groups[1])
            else:
                continue
            
            result = ParseResult(
                episode_number=ep_num,
                matched_text=match.group(0),
                confidence=confidence
            )
            
            if best_match is None or result.confidence > best_match.confidence:
                best_match = result
    
    return best_match


def parse_all_episodes(text: str) -> List[ParseResult]:
    """
    Parse all episode numbers found in text (for multi-episode posts).
    Returns list sorted by confidence (highest first), deduplicated by episode number.
    """
    results = []
    seen_episodes = set()
    
    for pattern, confidence in EPISODE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            groups = match.groups()
            if len(groups) == 1:
                ep_num = float(groups[0])
            elif len(groups) == 2:
                ep_num = float(groups[1])
            else:
                continue
            
            # Deduplicate by episode number - keep highest confidence
            if ep_num in seen_episodes:
                continue
            seen_episodes.add(ep_num)
            
            results.append(ParseResult(
                episode_number=ep_num,
                matched_text=match.group(0),
                confidence=confidence
            ))
    
    # Sort by confidence descending
    results.sort(key=lambda x: x.confidence, reverse=True)
    return results


def build_anime_link(channel: str, message_id: int) -> str:
    """
    Build a t.me link for a channel message.
    Handles both @channel and channel formats.
    """
    clean_channel = channel.lstrip('@')
    return f"https://t.me/{clean_channel}/{message_id}"


def extract_channel_name(text: str) -> Optional[str]:
    """
    Try to extract a channel username from a message forward or text.
    Returns channel name without @.
    """
    # Pattern for t.me links
    link_match = re.search(r't\.me/([a-zA-Z0-9_]+)/\d+', text)
    if link_match:
        return link_match.group(1)
    
    # Pattern for @channel mentions
    mention_match = re.search(r'@([a-zA-Z0-9_]{5,})', text)
    if mention_match:
        return mention_match.group(1)
    
    return None


if __name__ == "__main__":
    # Quick test
    test_messages = [
        "【JJK】Jujutsu Kaisen EP12 リリース！",
        "Episode 5 is out now",
        "[One Piece] 1080話 新章突入",
        "S01E24 - Final Episode",
        "第3話「出会い」",
        "제10화 공개",
        "#15 New episode available",
        "Chainsaw Man Ep 8",
        "【Demo】S02E05 [720p]",
    ]
    
    for msg in test_messages:
        result = parse_episode_number(msg)
        if result:
            print(f"'{msg}' -> Ep {result.episode_number} (conf: {result.confidence}, matched: '{result.matched_text}')")
        else:
            print(f"'{msg}' -> No match")
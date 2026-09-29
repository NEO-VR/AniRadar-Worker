#!/usr/bin/env python3
"""
تست‌های خودکار برای پارسر شماره قسمت و تطابق نام‌های مستعار
اجرای تست: python -m pytest tests/test_parser.py -v
"""

import sys
from pathlib import Path

# افزودن مسیر پروژه
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import parse_episode_number, match_aliases, normalize_text


def test_parse_standard_episode():
    """تفر استخراج شماره قسمت در فرمت‌های استاندارد."""
    assert parse_episode_number("Episode 12") is not None
    assert parse_episode_number("Episode 12").episode_number == 12
    assert parse_episode_number("EP 12").episode_number == 12
    assert parse_episode_number("قسمت 12").episode_number == 12


def test_parse_cjk_episode():
    """تست استخراج شماره قسمت در فرمت ژاپنی/چینی."""
    assert parse_episode_number("第12話").episode_number == 12
    assert parse_episode_number("第12集") is None or parse_episode_number("第12集").episode_number == 12


def test_parse_bracket_episode():
    """تست استخراج شماره قسمت در فرمت کروشه."""
    result = parse_episode_number("[12]")
    assert result is not None
    assert result.episode_number == 12


def test_parse_season_episode():
    """تست استخراج قسمت در فرمت فصل/قسمت."""
    result = parse_episode_number("S01E12")
    assert result is not None
    assert result.episode_number == 12


def test_parse_year_ignored():
    """سال‌های میلادی نباید به عنوان شماره قسمت تشخیص داده شوند."""
    # 1999 سال پخش One Piece است، نه شماره قسمت
    result = parse_episode_number("One Piece (1999)")
    if result is not None:
        assert not (1900 <= result.episode_number <= 2099), \
            f"سال {result.episode_number} نباید به عنوان قسمت تشخیص شود"


def test_parse_list_post_ignored():
    """پست‌های لیست پیشنهادات نباید شماره قسمت بدهند."""
    # لیست شماره‌دار چند انیمه
    result = parse_episode_number(
        "🎯 انیمه‌های پیشنهادی امروز\n"
        "#1. One Piece (1999)\n"
        "#2. Bleach (2004)\n"
        "#3. Naruto (2002)\n"
        "#4. Detective Conan (1996)"
    )
    assert result is None, "پست لیست پیشنهادات نباید قسمت تشخیص دهد"


def test_parse_multi_anime_post_ignored():
    """پست‌های چند-انیمه‌ای (Download Box) نباید شماره قسمت بدهند."""
    result = parse_episode_number(
        "📌 عنوان اثر: One Piece\n"
        "📥 Download Box\n"
        "🗂 Ep 1151-1175: Subs\n"
        "📤 Ep 1176: Sub V2\n"
        "📤 Ep 1177: Sub V2\n"
        "📤 Ep 1178: Sub V2\n"
        "📤 Ep 1179: Sub V2\n"
        "📤 Ep 1180: Sub V2"
    )
    assert result is None, "پست Download Box چند انیمه‌ای نباید قسمت تشخیص دهد"


def test_match_aliases_word_boundary():
    """تطابق نام مستعار باید مرز کلمه را رعایت کند."""
    # "demon" به تنهایی نباید برای "Demon Slayer" تطابق کند
    text = "شوالیه سنگین demon می‌کشد"
    matched = match_aliases(text, ["Demon Slayer"])
    assert "Demon Slayer" not in matched, \
        "alias دو کلمه‌ای نباید با کلمه واحد تطابق کند"


def test_match_aliases_exact():
    """تطابق نام مستعار دقیق باید کار کند."""
    text = "One Piece قسمت ۱۱۲۶"
    matched = match_aliases(text, ["One Piece", "OP"])
    assert "One Piece" in matched


def test_match_aliases_short_no_substring():
    """alias کوتاه نباید به‌صورت زیررشته در کلمه دیگر تطابق کند."""
    text = "Tsuihou sareta Tensei Juukishi"
    matched = match_aliases(text, ["SL", "DD", "DS", "OP"])
    assert len(matched) == 0, f"alias کوتاه نباید تطابق کند: {matched}"


def test_normalize_text():
    """نرمال‌سازی متن باید فاصله و علائم را حذف کند."""
    assert normalize_text("  One   Piece!  ") == "one piece"
    assert normalize_text("ون‌پیس") == normalize_text("ون پیس")

"""Text normalization and unique key generation."""

from __future__ import annotations

import hashlib
import re
import unicodedata

# NFKC already folds full-width ASCII to half-width AND half-width kana to
# full-width kana, so no separate kana pass is needed.
_WS_RE = re.compile(r"\s+")
# Stray backslashes leak in from Markdown-escaped source text (e.g. "\ルーミー").
_JUNK_RE = re.compile(r"\\+")

_NUMBER_LABEL_RE = re.compile(r"(?:車両番号|車輛番号|車種番号|登録番号)\s*")
# e.g. 青森501わ3843 / 弘前300わ203 / いわき500わ4222 / 仙台502わ・169
# The place name is bounded to 2-4 kanji/hiragana so a katakana model name
# running straight into the plate ("ヤリス八戸500わ8598") still splits.
_PLATE_RE = re.compile(r"([一-龥ぁ-ん]{2,4}[0-9]{1,3}[ぁ-ん]・?[0-9]{1,4})\s*$")
_TRAILING_NUM_RE = re.compile(r"^(.*?[^\s0-9])\s*([0-9]{2,})\s*$")

_PERIOD_RE = re.compile(
    r"([0-9]{4})年\s*([0-9]{1,2})月\s*([0-9]{1,2})日"
    r"\s*[～~〜\-—]\s*"
    r"(?:([0-9]{4})年\s*)?([0-9]{1,2})月\s*([0-9]{1,2})日"
)


def normalize(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = _JUNK_RE.sub("", s)
    return _WS_RE.sub(" ", s).strip()


def strip_parens(s: str) -> str:
    return normalize(s).strip("（）()").strip()


def split_car(text: str) -> tuple[str, str]:
    """Split '<車種> <車両番号>' into (model, number).

    Observed shapes: a label form (``ヤリス 車両番号3878``), a license plate
    (``ヤリス 青森501わ3843``), both at once (``カローラHV 車両番号山形300わ2156``),
    no separator (``ヤリス八戸500わ8598``) and no number at all
    (``乗用車（…店舗返却）``). The label is stripped first so the remaining text
    is always just "<model> <number>".
    """
    text = normalize(text)
    if not text:
        return "", ""

    text = normalize(_NUMBER_LABEL_RE.sub(" ", text))

    m = _PLATE_RE.search(text)
    if m:
        return text[: m.start()].strip(), m.group(1)

    # Parenthesised descriptions are prose, not a number.
    if not text.endswith(("）", ")")):
        m = _TRAILING_NUM_RE.match(text)
        if m:
            return m.group(1).strip(), m.group(2)

    return text, ""


def split_shop(text: str) -> tuple[str, str]:
    """Split '<運営会社> <店舗名>' into (company, shop)."""
    parts = normalize(text).split(" ", 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def parse_period(text: str) -> tuple[str, str]:
    """Parse '2026年9月7日 ～ 9月9日' into ISO dates.

    The end date omits the year on every listing observed, so it is carried from
    the start date and rolled forward when the period crosses New Year.
    """
    m = _PERIOD_RE.search(normalize(text))
    if not m:
        return "", ""
    y1, m1, d1, y2, m2, d2 = m.groups()
    start_y, start_m, start_d = int(y1), int(m1), int(d1)
    end_y = int(y2) if y2 else start_y
    end_m, end_d = int(m2), int(d2)
    if not y2 and (end_m, end_d) < (start_m, start_d):
        end_y += 1
    return (
        f"{start_y:04d}-{start_m:02d}-{start_d:02d}",
        f"{end_y:04d}-{end_m:02d}-{end_d:02d}",
    )


def make_key(
    depart_company: str,
    depart_shop: str,
    return_company: str,
    car_model: str,
    car_number: str,
    period_start: str,
    period_end: str,
) -> str:
    raw = "|".join(
        (
            normalize(depart_company),
            normalize(depart_shop),
            normalize(return_company),
            normalize(car_model),
            normalize(car_number),
            period_start,
            period_end,
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

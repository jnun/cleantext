#!/usr/bin/env python3
# Copyright (c) 2026 Jason Nunnelley
# SPDX-License-Identifier: MIT
"""
cleantext — strip Unicode-layer watermarks and fingerprinting artifacts from text.

Covers the format-based / steganographic marks commonly found in AI-generated or
AI-processed text: zero-width characters, variation selectors, alternate spaces,
homoglyph substitution, trailing-whitespace payload, and related control marks.

Does NOT remove generation-time watermarks (e.g. SynthID-style token bias, Claude
model-level text marks) or C2PA file metadata. Those require paraphrasing / rewrite
or separate metadata tools — see --limitations.

License: MIT (see LICENSE). Copyright remains with the originator.

Usage:
  python cleantext.py input.txt
  python cleantext.py input.txt -o clean.txt
  python cleantext.py input.txt --scan
  python cleantext.py input.txt --aggressive
  cat input.txt | python cleantext.py -
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Character sets used by common Unicode text watermark / stego schemes
# (AITSteg, CovertSYS, StegCloak, UniSpaCh, Innamark, Rizzo, LookALikes, SNOW, …)
# ---------------------------------------------------------------------------

# Invisible / zero-width / format marks frequently used as bit carriers
INVISIBLE_CHARS: frozenset[str] = frozenset(
    {
        "\u00ad",  # soft hyphen
        "\u034f",  # combining grapheme joiner
        "\u061c",  # Arabic letter mark
        "\u115f",  # Hangul choseong filler
        "\u1160",  # Hangul jungseong filler
        "\u17b4",  # Khmer vowel inherent aq
        "\u17b5",  # Khmer vowel inherent aa
        "\u180b",  # Mongolian free variation selector one
        "\u180c",  # Mongolian free variation selector two
        "\u180d",  # Mongolian free variation selector three
        "\u180e",  # Mongolian vowel separator
        "\u180f",  # Mongolian free variation selector four
        "\u200b",  # zero-width space
        "\u200c",  # zero-width non-joiner
        "\u200d",  # zero-width joiner
        "\u200e",  # left-to-right mark
        "\u200f",  # right-to-left mark
        "\u202a",  # left-to-right embedding
        "\u202b",  # right-to-left embedding
        "\u202c",  # pop directional formatting
        "\u202d",  # left-to-right override
        "\u202e",  # right-to-left override
        "\u2060",  # word joiner
        "\u2061",  # function application
        "\u2062",  # invisible times
        "\u2063",  # invisible separator
        "\u2064",  # invisible plus
        "\u2065",  # invisible times (reserved)
        "\u2066",  # left-to-right isolate
        "\u2067",  # right-to-left isolate
        "\u2068",  # first strong isolate
        "\u2069",  # pop directional isolate
        "\u206a",  # inhibit symmetric swapping
        "\u206b",  # activate symmetric swapping
        "\u206c",  # inhibit Arabic form shaping
        "\u206d",  # activate Arabic form shaping
        "\u206e",  # national digit shapes
        "\u206f",  # nominal digit shapes
        "\ufeff",  # zero-width no-break space / BOM
        "\ufff9",  # interlinear annotation anchor
        "\ufffa",  # interlinear annotation separator
        "\ufffb",  # interlinear annotation terminator
    }
)

# Alternate whitespace characters (Innamark, UniSpaCh, Rizzo, SNOW-adjacent)
# Mapped to regular ASCII space U+0020 (or removed when trailing-only).
SPACE_VARIANTS: dict[str, str] = {
    "\u00a0": " ",  # no-break space
    "\u1680": " ",  # Ogham space mark
    "\u2000": " ",  # en quad
    "\u2001": " ",  # em quad
    "\u2002": " ",  # en space
    "\u2003": " ",  # em space
    "\u2004": " ",  # three-per-em space
    "\u2005": " ",  # four-per-em space
    "\u2006": " ",  # six-per-em space
    "\u2007": " ",  # figure space
    "\u2008": " ",  # punctuation space
    "\u2009": " ",  # thin space
    "\u200a": " ",  # hair space
    "\u202f": " ",  # narrow no-break space
    "\u205f": " ",  # medium mathematical space
    "\u3000": " ",  # ideographic space
    "\u2800": " ",  # braille pattern blank (sometimes abused as space)
}

# Common Latin-script confusables / homoglyphs used by LookALikes, Rizzo, etc.
# Maps lookalikes → ASCII Latin. Intentionally conservative (letters only).
HOMOGLYPH_MAP: dict[str, str] = {
    # Cyrillic → Latin
    "\u0410": "A",  # А
    "\u0412": "B",  # В
    "\u0415": "E",  # Е
    "\u041a": "K",  # К
    "\u041c": "M",  # М
    "\u041d": "H",  # Н
    "\u041e": "O",  # О
    "\u0420": "P",  # Р
    "\u0421": "C",  # С
    "\u0422": "T",  # Т
    "\u0425": "X",  # Х
    "\u0430": "a",  # а
    "\u0435": "e",  # е
    "\u043e": "o",  # о
    "\u0440": "p",  # р
    "\u0441": "c",  # с
    "\u0443": "y",  # у
    "\u0445": "x",  # х
    "\u0456": "i",  # і (Ukrainian)
    "\u04bb": "h",  # һ
    # Greek → Latin
    "\u0391": "A",  # Α
    "\u0392": "B",  # Β
    "\u0395": "E",  # Ε
    "\u0397": "H",  # Η
    "\u0399": "I",  # Ι
    "\u039a": "K",  # Κ
    "\u039c": "M",  # Μ
    "\u039d": "N",  # Ν
    "\u039f": "O",  # Ο
    "\u03a1": "P",  # Ρ
    "\u03a4": "T",  # Τ
    "\u03a5": "Y",  # Υ
    "\u03a7": "X",  # Χ
    "\u03b1": "a",  # α
    "\u03b9": "i",  # ι
    "\u03ba": "k",  # κ
    "\u03bd": "v",  # ν
    "\u03bf": "o",  # ο
    "\u03c1": "p",  # ρ
    "\u03c4": "t",  # τ
    "\u03c5": "u",  # υ
    "\u03c7": "x",  # χ
    # Fullwidth Latin
    **{chr(0xFF21 + i): chr(ord("A") + i) for i in range(26)},
    **{chr(0xFF41 + i): chr(ord("a") + i) for i in range(26)},
    **{chr(0xFF10 + i): chr(ord("0") + i) for i in range(10)},
    # Mathematical / script / double-struck lookalikes (common confusables)
    "\u2102": "C",  # ℂ
    "\u2107": "E",  # ℇ
    "\u210a": "g",  # ℊ
    "\u210b": "H",  # ℋ
    "\u210c": "H",  # ℌ
    "\u210d": "H",  # ℍ
    "\u210e": "h",  # ℎ
    "\u2110": "I",  # ℐ
    "\u2111": "I",  # ℑ
    "\u2112": "L",  # ℒ
    "\u2113": "l",  # ℓ
    "\u2115": "N",  # ℕ
    "\u2119": "P",  # ℙ
    "\u211a": "Q",  # ℚ
    "\u211b": "R",  # ℛ
    "\u211c": "R",  # ℜ
    "\u211d": "R",  # ℝ
    "\u2124": "Z",  # ℤ
    "\u212c": "B",  # ℬ
    "\u2130": "E",  # ℰ
    "\u2131": "F",  # ℱ
    "\u2133": "M",  # ℳ
    # Latin confusables with diacritic-like presentation often used as bits
    "\u0131": "i",  # ı (dotless i) — sometimes used as confusable
    "\u0237": "j",  # ȷ
}

# Punctuation / quote / dash normalization (aggressive mode + default light set)
PUNCT_MAP: dict[str, str] = {
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
    "\u201a": "'",  # ‚
    "\u201b": "'",  # ‛
    "\u2032": "'",  # ′
    "\u02bc": "'",  # ʼ (modifier letter apostrophe — Claude Code marker)
    "\u02b9": "'",  # ʹ (modifier letter prime — Claude Code marker)
    "\u201c": '"',  # “
    "\u201d": '"',  # ”
    "\u201e": '"',  # „
    "\u201f": '"',  # ‟
    "\u2033": '"',  # ″
    "\u00ab": '"',  # «
    "\u00bb": '"',  # »
    "\u2010": "-",  # ‐ hyphen
    "\u2011": "-",  # ‑ non-breaking hyphen
    "\u2012": "-",  # ‒ figure dash
    "\u2013": "-",  # – en dash
    "\u2014": "-",  # — em dash
    "\u2015": "-",  # ― horizontal bar
    "\u2212": "-",  # − minus
    "\u2026": "...",  # …
    "\u00b7": ".",  # · middle dot (sometimes abused)
}


def _is_variation_selector(cp: int) -> bool:
    return (0xFE00 <= cp <= 0xFE0F) or (0xE0100 <= cp <= 0xE01EF)


def _is_tag_char(cp: int) -> bool:
    # Unicode Tags block — used in some stego / invisible-payload schemes
    return 0xE0000 <= cp <= 0xE007F


def _is_c0_c1_control(cp: int) -> bool:
    # Keep common whitespace controls: TAB, LF, CR
    if cp in (0x09, 0x0A, 0x0D):
        return False
    return (0x00 <= cp <= 0x08) or (0x0B <= cp <= 0x1F) or (0x7F <= cp <= 0x9F)


def _char_label(ch: str) -> str:
    cp = ord(ch)
    name = unicodedata.name(ch, "UNKNOWN")
    cat = unicodedata.category(ch)
    return f"U+{cp:04X} {name} [{cat}]"


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    kind: str
    count: int
    samples: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class ScanReport:
    total_chars: int
    findings: list[Finding]
    risk_score: int  # rough 0–100 heuristic

    @property
    def total_suspicious(self) -> int:
        return sum(f.count for f in self.findings)

    def is_clean(self) -> bool:
        return self.total_suspicious == 0


def scan_text(text: str) -> ScanReport:
    """Detect Unicode artifacts commonly used for watermarking / fingerprinting."""
    findings: list[Finding] = []
    inv = Counter()
    spaces = Counter()
    glyphs = Counter()
    punct = Counter()
    vs = 0
    tags = 0
    controls = 0
    trailing_ws_lines = 0
    odd_cf = Counter()

    lines = text.splitlines(keepends=True)
    for line in lines:
        body = line.rstrip("\r\n")
        if body != body.rstrip(" \t"):
            trailing_ws_lines += 1

    for ch in text:
        cp = ord(ch)

        if ch in INVISIBLE_CHARS:
            inv[ch] += 1
        elif _is_variation_selector(cp):
            vs += 1
        elif _is_tag_char(cp):
            tags += 1
        elif _is_c0_c1_control(cp):
            controls += 1
        elif ch in SPACE_VARIANTS:
            spaces[ch] += 1
        elif ch in HOMOGLYPH_MAP:
            glyphs[ch] += 1
        elif ch in PUNCT_MAP:
            punct[ch] += 1
        else:
            # Other Cf (format) characters not in our explicit list
            if unicodedata.category(ch) == "Cf" and ch not in ("\n", "\r", "\t"):
                odd_cf[ch] += 1

    def _add(kind: str, counter: Counter, detail: str = "") -> None:
        total = sum(counter.values())
        if total:
            samples = [
                f"{_char_label(c)} ×{n}" for c, n in counter.most_common(8)
            ]
            findings.append(Finding(kind, total, samples, detail))

    _add(
        "invisible/zero-width",
        inv,
        "Classic zero-width / bidi / soft-hyphen payload carriers (StegCloak, AITSteg, …)",
    )
    if vs:
        findings.append(
            Finding(
                "variation selectors",
                vs,
                detail="VS1–VS256; can encode bits without visible change",
            )
        )
    if tags:
        findings.append(
            Finding(
                "unicode tags block",
                tags,
                detail="U+E0000–U+E007F invisible tag characters",
            )
        )
    if controls:
        findings.append(
            Finding(
                "C0/C1 controls",
                controls,
                detail="Non-whitespace control characters (excluding TAB/LF/CR)",
            )
        )
    _add(
        "alternate spaces",
        spaces,
        "Non-ASCII spaces used by Innamark / UniSpaCh / whitespace stego",
    )
    _add(
        "homoglyphs",
        glyphs,
        "Confusable lookalikes (Cyrillic/Greek/fullwidth/math) used by LookALikes / Rizzo",
    )
    _add(
        "fancy punctuation",
        punct,
        "Smart quotes / dashes / special apostrophes (sometimes used as side-channel marks)",
    )
    _add("other format (Cf)", odd_cf)
    if trailing_ws_lines:
        findings.append(
            Finding(
                "trailing whitespace lines",
                trailing_ws_lines,
                detail="Trailing spaces/tabs on lines — used by SNOW and similar",
            )
        )

    # Heuristic risk score
    score = 0
    weights = {
        "invisible/zero-width": 8,
        "variation selectors": 8,
        "unicode tags block": 10,
        "C0/C1 controls": 5,
        "alternate spaces": 4,
        "homoglyphs": 5,
        "fancy punctuation": 1,
        "other format (Cf)": 6,
        "trailing whitespace lines": 3,
    }
    for f in findings:
        score += min(40, f.count * weights.get(f.kind, 2))
    score = min(100, score)

    return ScanReport(total_chars=len(text), findings=findings, risk_score=score)


def format_report(report: ScanReport, path: str | None = None) -> str:
    header = f"Scan: {path}" if path else "Scan: <stdin>"
    lines = [
        header,
        f"  Characters: {report.total_chars:,}",
        f"  Suspicious: {report.total_suspicious:,}",
        f"  Risk score: {report.risk_score}/100 "
        f"({'clean' if report.is_clean() else 'artifacts present'})",
        "",
    ]
    if report.is_clean():
        lines.append("  No Unicode-layer watermark artifacts detected.")
        return "\n".join(lines)

    for f in report.findings:
        lines.append(f"  [{f.kind}] count={f.count}")
        if f.detail:
            lines.append(f"    {f.detail}")
        for s in f.samples:
            lines.append(f"    - {s}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


@dataclass
class CleanStats:
    removed_invisible: int = 0
    removed_vs: int = 0
    removed_tags: int = 0
    removed_controls: int = 0
    normalized_spaces: int = 0
    normalized_homoglyphs: int = 0
    normalized_punct: int = 0
    stripped_trailing_ws: int = 0
    nfkc_changed: bool = False
    original_len: int = 0
    cleaned_len: int = 0

    @property
    def total_changes(self) -> int:
        return (
            self.removed_invisible
            + self.removed_vs
            + self.removed_tags
            + self.removed_controls
            + self.normalized_spaces
            + self.normalized_homoglyphs
            + self.normalized_punct
            + self.stripped_trailing_ws
            + (1 if self.nfkc_changed else 0)
        )


def clean_text(
    text: str,
    *,
    aggressive: bool = False,
    normalize_homoglyphs: bool = True,
    normalize_punctuation: bool = True,
    strip_trailing_whitespace: bool = True,
    unicode_form: str | None = "NFKC",
) -> tuple[str, CleanStats]:
    """
    Strip / normalize Unicode-layer watermark artifacts.

    Parameters
    ----------
    aggressive:
        Also strip any remaining Cf-category characters and apply broader
        NFKC-driven collapse. Prefer default first for mixed natural-language text.
    unicode_form:
        unicodedata form, or None to skip normalization.
    """
    stats = CleanStats(original_len=len(text))
    out: list[str] = []

    for ch in text:
        cp = ord(ch)

        if ch in INVISIBLE_CHARS:
            stats.removed_invisible += 1
            continue
        if _is_variation_selector(cp):
            stats.removed_vs += 1
            continue
        if _is_tag_char(cp):
            stats.removed_tags += 1
            continue
        if _is_c0_c1_control(cp):
            stats.removed_controls += 1
            continue
        if aggressive and unicodedata.category(ch) == "Cf":
            stats.removed_invisible += 1
            continue

        if ch in SPACE_VARIANTS:
            stats.normalized_spaces += 1
            out.append(SPACE_VARIANTS[ch])
            continue

        if normalize_homoglyphs and ch in HOMOGLYPH_MAP:
            stats.normalized_homoglyphs += 1
            out.append(HOMOGLYPH_MAP[ch])
            continue

        if normalize_punctuation and ch in PUNCT_MAP:
            stats.normalized_punct += 1
            out.append(PUNCT_MAP[ch])
            continue

        out.append(ch)

    result = "".join(out)

    if strip_trailing_whitespace:
        cleaned_lines: list[str] = []
        for line in result.splitlines(keepends=True):
            if line.endswith("\r\n"):
                body, ending = line[:-2], "\r\n"
            elif line.endswith("\n"):
                body, ending = line[:-1], "\n"
            elif line.endswith("\r"):
                body, ending = line[:-1], "\r"
            else:
                body, ending = line, ""
            stripped = body.rstrip(" \t")
            stats.stripped_trailing_ws += len(body) - len(stripped)
            cleaned_lines.append(stripped + ending)
        # Preserve whether original ended with a newline (splitlines keepends path)
        if result and not result.endswith(("\n", "\r")):
            # last line had no newline; splitlines already handled it without ending
            pass
        result = "".join(cleaned_lines)

    if unicode_form:
        normalized = unicodedata.normalize(unicode_form, result)
        if normalized != result:
            stats.nfkc_changed = True
            result = normalized

    stats.cleaned_len = len(result)
    return result, stats


def format_stats(stats: CleanStats) -> str:
    lines = [
        "Clean summary:",
        f"  Original length : {stats.original_len:,}",
        f"  Cleaned length  : {stats.cleaned_len:,}",
        f"  Delta           : {stats.original_len - stats.cleaned_len:+,}",
        f"  Removed invisible/ZW : {stats.removed_invisible}",
        f"  Removed var. selectors: {stats.removed_vs}",
        f"  Removed tag chars     : {stats.removed_tags}",
        f"  Removed C0/C1 controls: {stats.removed_controls}",
        f"  Normalized spaces     : {stats.normalized_spaces}",
        f"  Normalized homoglyphs : {stats.normalized_homoglyphs}",
        f"  Normalized punctuation: {stats.normalized_punct}",
        f"  Trailing WS stripped  : {stats.stripped_trailing_ws}",
        f"  Unicode normalize     : {'yes' if stats.nfkc_changed else 'no change'}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Synthetic watermark helpers (for self-test / demos)
# ---------------------------------------------------------------------------


def inject_zero_width_payload(text: str, bits: str = "10110010") -> str:
    """Embed a tiny zero-width bit string after the first word (StegCloak-style)."""
    mapping = {"0": "\u200c", "1": "\u200d"}  # ZWNJ / ZWJ
    payload = "\u200b" + "".join(mapping[b] for b in bits if b in mapping) + "\u200b"
    parts = text.split(" ", 1)
    if len(parts) == 1:
        return text + payload
    return parts[0] + payload + " " + parts[1]


def inject_homoglyphs(text: str, every: int = 3) -> str:
    """Replace some Latin letters with Cyrillic/Greek lookalikes."""
    reverse = {
        "A": "\u0410",
        "B": "\u0412",
        "E": "\u0415",
        "O": "\u041e",
        "P": "\u0420",
        "C": "\u0421",
        "a": "\u0430",
        "e": "\u0435",
        "o": "\u043e",
        "p": "\u0440",
        "c": "\u0441",
        "x": "\u0445",
    }
    out: list[str] = []
    n = 0
    for ch in text:
        if ch in reverse:
            n += 1
            if n % every == 0:
                out.append(reverse[ch])
                continue
        out.append(ch)
    return "".join(out)


def inject_space_variants(text: str) -> str:
    """Replace every 3rd regular space with a three-per-em space (Innamark-ish)."""
    out: list[str] = []
    n = 0
    for ch in text:
        if ch == " ":
            n += 1
            out.append("\u2004" if n % 3 == 0 else " ")
        else:
            out.append(ch)
    return "".join(out)


def inject_trailing_snow(text: str, bits: str = "1101001") -> str:
    """Append trailing spaces/tabs encoding bits (SNOW-style)."""
    lines = text.splitlines()
    if not lines:
        return text
    encoded = "".join(("  " if b == "1" else " \t") for b in bits)
    lines[-1] = lines[-1].rstrip() + encoded
    ending = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + ending


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

LIMITATIONS = """
LIMITATIONS
===========
What this tool removes (Unicode / format-layer):
  • Zero-width and invisible characters (ZWSP, ZWNJ, ZWJ, WJ, soft hyphen, …)
  • Bidirectional control marks and isolates
  • Variation selectors and Unicode Tags block
  • Alternate / steganographic whitespace (NBSP, three-per-em, ideographic, …)
  • Common Latin confusable homoglyphs (Cyrillic/Greek/fullwidth/math lookalikes)
  • Smart quotes, special apostrophes, fancy dashes (optional)
  • Trailing whitespace payloads (SNOW-style)
  • Optional NFKC Unicode normalization

What this tool cannot remove (generation-layer / metadata):
  • SynthID-style token-sampling watermarks (Google and similar research methods)
  • Cryptographic green/red list biases baked into next-token choice
  • Claude model-level embedded text watermark (see below)
  • Stylometric "fingerprints" from model writing habits
  • C2PA / signed provenance metadata on files (not present in plain text)

Anthropic (Claude) note (as of Aug 2026):
  Help Center: "How Claude marks AI-generated content"
  https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content

  Two official layers:
    1) Imperceptible watermark woven into text at the model level
       (models launched on/after 2026-08-02; older models in transition).
       Travels with copy-paste; may survive some editing. Encoding and
       public detection details are "forthcoming" — treat as generation-time
       / Claude-class signal, not documented Unicode stego.
    2) C2PA signed provenance on supported files (e.g. SVG, PNG, JPG).

  cleantext strips Unicode-layer artifacts if they appear in the string
  (invisible codepoints, alternate spaces, homoglyphs, special apostrophes,
  trailing-WS payloads, …). It does not remove the official model-level
  text watermark. Heavy rewrite / paraphrase (different model or human),
  short text, or pre-marking models weaken that signal per Anthropic.

Honest expectation:
  Unicode cleanup is deterministic and highly effective against format-based
  stego. Generation-time watermarks need content change (paraphrase), not
  character scrubbing.
""".strip()


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _write_output(path: str | None, text: str) -> None:
    if path is None or path == "-":
        sys.stdout.write(text)
        if text and not text.endswith("\n"):
            sys.stdout.write("\n")
        return
    Path(path).write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cleantext",
        description="Strip Unicode-layer watermarks / fingerprinting artifacts from text.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  cleantext.py draft.txt -o draft.clean.txt\n"
        "  cleantext.py draft.txt --scan\n"
        "  cleantext.py draft.txt --aggressive --stats\n"
        "  cat draft.txt | cleantext.py - > clean.txt\n",
    )
    p.add_argument(
        "input",
        nargs="?",
        help="Input file path, or '-' for stdin (not required with --self-test / --limitations)",
    )
    p.add_argument(
        "-o",
        "--output",
        help="Output file path (default: stdout for clean; ignored with --scan)",
    )
    p.add_argument(
        "--scan",
        action="store_true",
        help="Only scan and report suspicious characters; do not write cleaned text",
    )
    p.add_argument(
        "--aggressive",
        action="store_true",
        help="Also strip residual Cf-category characters",
    )
    p.add_argument(
        "--no-homoglyphs",
        action="store_true",
        help="Do not map confusable lookalikes to ASCII Latin",
    )
    p.add_argument(
        "--no-punct",
        action="store_true",
        help="Do not normalize smart quotes / dashes / special apostrophes",
    )
    p.add_argument(
        "--keep-trailing-ws",
        action="store_true",
        help="Do not strip trailing spaces/tabs on lines",
    )
    p.add_argument(
        "--no-nfkc",
        action="store_true",
        help="Skip Unicode NFKC normalization",
    )
    p.add_argument(
        "--stats",
        action="store_true",
        help="Print cleaning statistics to stderr",
    )
    p.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input file with cleaned text",
    )
    p.add_argument(
        "--limitations",
        action="store_true",
        help="Print what this tool can and cannot remove, then exit",
    )
    p.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in effectiveness checks and exit",
    )
    return p


def run_self_test() -> int:
    """Inject synthetic watermarks, clean, and verify removal."""
    base = (
        "The quick brown fox jumps over the lazy dog.\n"
        "Pack my box with five dozen liquor jugs.\n"
    )
    cases: list[tuple[str, str]] = [
        ("zero-width payload", inject_zero_width_payload(base)),
        ("homoglyphs", inject_homoglyphs(base)),
        ("space variants", inject_space_variants(base)),
        ("trailing SNOW", inject_trailing_snow(base)),
        (
            "combined",
            inject_trailing_snow(
                inject_space_variants(
                    inject_homoglyphs(inject_zero_width_payload(base))
                )
            ),
        ),
    ]

    # Also plant variation selectors + tag chars + fancy apostrophe
    planted = (
        "Today\u2019s date is clean.\u200b\ufe0e"
        + "\U000e0061"  # tag letter a
        + " Normal text.\n"
    )
    cases.append(("vs+tags+apostrophe", planted))

    failed = 0
    print("Self-test: synthetic watermark injection → clean → re-scan\n")

    for name, dirty in cases:
        before = scan_text(dirty)
        cleaned, stats = clean_text(dirty)
        after = scan_text(cleaned)

        # After full clean, risk should be 0 for these synthetic cases
        ok = after.is_clean()

        # Content sanity: core letters preserved for base-derived cases
        if name != "vs+tags+apostrophe":
            core_ok = "quick brown fox" in cleaned.lower() or "Quick" in cleaned
        else:
            core_ok = "Today" in cleaned and "Normal text" in cleaned

        status = "PASS" if ok and core_ok else "FAIL"
        if status == "FAIL":
            failed += 1

        print(f"  [{status}] {name}")
        print(
            f"         before risk={before.risk_score} "
            f"suspicious={before.total_suspicious} → "
            f"after risk={after.risk_score} suspicious={after.total_suspicious} "
            f"(Δ chars {stats.original_len - stats.cleaned_len:+d})"
        )
        if not ok:
            print(f"         residual findings: {[f.kind for f in after.findings]}")
            print(format_report(after))

    # Round-trip: clean text stays clean
    clean_base, _ = clean_text(base)
    rt = scan_text(clean_base)
    status = "PASS" if rt.is_clean() else "FAIL"
    if status == "FAIL":
        failed += 1
    print(f"  [{status}] clean input stays clean")

    print()
    if failed:
        print(f"RESULT: {failed} failure(s)")
        return 1
    print("RESULT: all checks passed")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.limitations:
        print(LIMITATIONS)
        return 0

    if args.self_test:
        return run_self_test()

    if not args.input:
        parser.error("input is required (or use --self-test / --limitations)")

    if args.in_place and args.input == "-":
        parser.error("--in-place cannot be used with stdin")
    if args.in_place and args.output:
        parser.error("--in-place and --output are mutually exclusive")

    try:
        text = _read_input(args.input)
    except OSError as e:
        print(f"error: cannot read {args.input!r}: {e}", file=sys.stderr)
        return 2

    label = args.input if args.input != "-" else None

    if args.scan:
        report = scan_text(text)
        sys.stdout.write(format_report(report, label))
        return 0 if report.is_clean() else 1

    cleaned, stats = clean_text(
        text,
        aggressive=args.aggressive,
        normalize_homoglyphs=not args.no_homoglyphs,
        normalize_punctuation=not args.no_punct,
        strip_trailing_whitespace=not args.keep_trailing_ws,
        unicode_form=None if args.no_nfkc else "NFKC",
    )

    out_path = args.input if args.in_place else args.output
    try:
        _write_output(out_path, cleaned)
    except OSError as e:
        print(f"error: cannot write output: {e}", file=sys.stderr)
        return 2

    if args.stats or args.in_place:
        print(format_stats(stats), file=sys.stderr)
        post = scan_text(cleaned)
        if not post.is_clean():
            print(
                "warning: residual artifacts remain "
                f"(risk={post.risk_score}); try --aggressive",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

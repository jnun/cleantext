# cleantext

**cleantext** is a small Python CLI and library that removes **Unicode-layer watermarks and fingerprinting artifacts** from plain text.

Use it when AI-generated or AI-edited writing may still carry invisible codepoints, lookalike characters, or steganographic whitespace — even after human editing.

| | |
| --- | --- |
| **Status** | Alpha (`0.1.0`) |
| **Python** | 3.10+ |
| **Dependencies** | None (stdlib only) |
| **License** | MIT |

---

## What this project does (current)

Given a text file (or stdin), cleantext:

1. **Scans** for suspicious Unicode artifacts used by format-based watermarking / steganography
2. **Strips or normalizes** those artifacts into plain, readable text
3. **Reports** what changed (optional stats) and a simple risk score on scan

### Removes / normalizes today

| Category | Examples |
| --- | --- |
| Invisible / zero-width | ZWSP `U+200B`, ZWNJ, ZWJ, word joiner, soft hyphen, BOM |
| Bidi controls | LRM/RLM, embeddings, overrides, isolates |
| Variation selectors & Tags | `U+FE00–U+FE0F`, `U+E0100–U+E01EF`, Tags `U+E0000–U+E007F` |
| Alternate spaces | NBSP, three-per-em, ideographic space, hair/thin spaces, … |
| Homoglyphs | Cyrillic/Greek/fullwidth/math lookalikes of Latin letters |
| Fancy punctuation | Smart quotes, special apostrophes, en/em dashes → ASCII |
| Trailing whitespace payloads | End-of-line spaces/tabs (SNOW-style) |
| Unicode form | Optional **NFKC** normalization |

### Does **not** remove (by design)

| Category | Why |
| --- | --- |
| Generation-time text marks (Kirchenbauer, SynthID-Text, Claude model-level) | Signal woven in during decoding; only substantial rewrite degrades it |
| Imperceptible media watermarks (SynthID image/video/audio) | Not plain text |
| C2PA / EXIF / signed provenance | File metadata, not the string |
| Visible AI labels / EU disclosure icons | Human-facing UI, not Unicode stego |
| Stylometric “sounds like AI” classifiers | Not embedded characters |

> **Honest scope:** Excellent against format-based Unicode stego. Not a claim of “undetectable human text” or defeat of statistical / multi-layer lab marking.

For the full catalog of methods (regulatory context, text, media, metadata, labels), see **[METHODS.md](METHODS.md)**.
---

## Install

From the project root (use a venv on Homebrew/PEP 668 systems):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# editable install (recommended while developing)
pip install -e .

# or with test extras
pip install -e ".[dev]"
```

After install, the `cleantext` command is on your `PATH`:

```bash
cleantext --help
```

Without installing, you can still run the module directly:

```bash
python cleantext.py --help
```

---

## Quick start

```bash
# Inspect a file (exit 1 if artifacts found)
cleantext notes.txt --scan

# Clean to a new file
cleantext notes.txt -o notes.clean.txt --stats

# Overwrite in place
cleantext notes.txt --in-place --stats

# Stdin / stdout (macOS pasteboard example)
pbpaste | cleantext - | pbcopy

# Built-in capability notes
cleantext --limitations

# Synthetic watermark effectiveness check
cleantext --self-test
```

### Library use

```python
from cleantext import clean_text, scan_text

report = scan_text(raw_text)
if not report.is_clean():
    print(report.risk_score, [f.kind for f in report.findings])

cleaned, stats = clean_text(raw_text)
print(stats.total_changes, cleaned)
```

---

## CLI reference

```text
cleantext [INPUT] [options]
```

| Flag | Description |
| --- | --- |
| `INPUT` | File path, or `-` for stdin |
| `-o`, `--output` | Write cleaned text here (default: stdout) |
| `--scan` | Report only; do not clean (exit `1` if suspicious) |
| `--in-place` | Overwrite the input file |
| `--stats` | Print cleaning summary to stderr |
| `--aggressive` | Also strip residual Unicode `Cf` format characters |
| `--no-homoglyphs` | Keep confusable lookalikes |
| `--no-punct` | Keep smart quotes / fancy dashes / special apostrophes |
| `--keep-trailing-ws` | Keep end-of-line spaces/tabs |
| `--no-nfkc` | Skip NFKC normalization |
| `--limitations` | Print what is / isn’t covered |
| `--self-test` | Run built-in injection → clean → re-scan checks |

---

## Project layout

```text
cleantext/
├── cleantext.py      # CLI + library (single module)
├── pyproject.toml    # packaging, entry point, tool config
├── README.md         # this file
├── METHODS.md        # how text watermarks work (by method family)
├── LICENSE
├── examples/         # sample dirty/clean text
└── tests/            # unit tests
```
---

## Development

```bash
pip install -e ".[dev]"

# unit tests (unittest or pytest)
python -m unittest tests.test_cleantext -v
pytest

# built-in effectiveness self-test
cleantext --self-test
```

No runtime third-party packages. Optional `pytest` is only for the `dev` extra.

---

## Background (short)

Providers often use a **multi-layered** stack for EU AI Act–style transparency (machine-readable marking of synthetic content): signed metadata (C2PA), imperceptible watermarks, and sometimes visible labels. Free-form text usually depends on a **generation-time watermark** because it cannot carry file metadata. People still also use or encounter **post-hoc Unicode stego** (zero-width characters, homoglyphs, etc.).

| What people call a “watermark” | Role | cleantext? |
| --- | --- | --- |
| Unicode / format stego | Invisible or lookalike characters in the string | **Yes** |
| Generation-time text marks (Kirchenbauer, SynthID-Text, Claude-class) | Signal woven into the text during decoding / model output | No — rewrite |
| Media signal marks | SynthID-style image/video/audio | No |
| C2PA / EXIF provenance | Signed or simple file metadata | No |
| Visible labels / icons | Human disclosure | No |
| Stylometry | Classifier “AI-like” style | No |

### Claude / Anthropic (as of Aug 2026)

Anthropic documents machine-readable marking under the EU AI Act Article 50(2) Code of Practice on Transparency of AI-Generated Content. Public description:

| Layer | What Anthropic says | cleantext? |
| --- | --- | --- |
| **Embedded text watermark** | Imperceptible mark **woven into the text at the model level**; no visible change to meaning/quality; travels with copy-paste; may persist through some editing | **No** — not a character scrub |
| **Signed provenance (C2PA)** | On supported generated files (e.g. SVG, PNG, JPG) | **No** — file metadata |

**Coverage (per Anthropic help center):** models launched **on or after 2 Aug 2026** support marking at launch; pre-date models are in a transition period. Marks apply across Claude products (API/Platform, Claude, Claude Code, Claude Cowork, Claude Tag) and via cloud partners, **worldwide**. Detection mechanisms and exact encoding details are **forthcoming** — treat the official text mark as a **generation-time / Claude-class** signal, not as documented Unicode stego.

**What cleantext still helps with on Claude output:** any **Unicode-layer** artifacts that appear in plain text (zero-width/invisible codepoints, alternate spaces, homoglyphs, special apostrophes such as modifier-letter forms sometimes seen in tooling, trailing whitespace payloads). Those are separate from the official model-level watermark.

**What degrades the official Claude text mark (per Anthropic’s own limitations):** heavy edit / paraphrase / translation / mixing into other writing; very short passages; models that did not yet support marking; unsupported surfaces. That is rewrite territory — not something a scrubber can promise.

Source: [How Claude marks AI-generated content](https://support.claude.com/en/articles/16266773-how-claude-marks-ai-generated-content) (Anthropic Help Center).

### Full methods catalog

**→ [METHODS.md](METHODS.md)** — EU/Code of Practice context; statistical text schemes; Claude marking detail; C2PA; media SynthID; visible labels; Unicode stego detail; detection reality; workflow

```bash
cleantext --limitations   # short in-CLI capability statement
```

---

## Changelog

### Docs (2026-08)

- Aligned Claude / Anthropic notes with the public Help Center article on AI content marking (model-level text watermark + C2PA; detection details forthcoming)
- Clarified that cleantext covers Unicode-layer artifacts only; official Claude embedded text marks need rewrite, not char scrub

### 0.1.0

- Initial release
- Scan + clean CLI (`cleantext`)
- Library API: `scan_text`, `clean_text`
- Covers zero-width/invisible, bidi, VS/Tags, space variants, homoglyphs, punctuation normalize, trailing WS, NFKC
- Built-in `--self-test` with synthetic watermarks
- Stdlib-only; packaged via `pyproject.toml`

<!-- Add new versions above this line as the project grows. -->

---

## Roadmap (ideas, not commitments)

Possible future work — track here as the project evolves:

- [ ] Batch / directory mode
- [ ] Configurable allow/deny character lists
- [ ] JSON scan report for tooling
- [ ] Optional paraphrase helper (statistical marks only; would need an LLM)
- [ ] Publish to PyPI

---

## License & authorship

This project is released under the **MIT License**. Full text: [LICENSE](LICENSE).

**Copyright (c) 2026 Jason Nunnelley.**

Copyright and ownership of this software remain with the **originator of the work** — the person who conceived it, directed it, and paid for any tools used to help write or edit it. Using an editor, spellchecker, or AI assistant does not transfer ownership of the resulting code or documentation to the vendor of that tool, any more than writing a book in Microsoft Word makes the book Microsoft’s property.

The MIT License is a **permission grant to others**, not a transfer of your copyright:

- You keep the copyright.
- Others may use, copy, modify, merge, publish, distribute, sublicense, and sell the Software **provided they keep the copyright notice and license text**.
- The software is provided “as is,” without warranty.

When you publish or redistribute this project (or a derivative), keep the copyright line and MIT notice intact so credit and ownership stay clear.

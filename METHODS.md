# AI watermarking and marking methods

This note catalogs techniques AI providers use to mark synthetic content — especially to meet **EU AI Act transparency** expectations (Article 50 and related guidance) and to make outputs detectable “in the wild.” Use it to understand **what `cleantext` can and cannot address**.

`cleantext` targets **Unicode / format steganography in plain text only**. Everything else below is context: statistical generation marks, C2PA, media watermarks, visible labels, and emerging methods are **not** removed by this tool.

---

## Regulatory and industry context (high level)

Providers of generative systems are expected to ensure synthetic **audio, image, video, and text** outputs are marked in a **machine-readable** way and detectable as artificially generated or manipulated. Techniques are judged against goals such as **effectiveness, interoperability, robustness, and reliability**.

No single method currently satisfies all four criteria perfectly. Industry practice and the voluntary **Code of Practice on Transparency of AI-Generated Content** (finalized around mid-2026) therefore favor a **multi-layered approach**. Typical combinations:

| Layer | Role |
| --- | --- |
| **Digitally signed metadata** (e.g. C2PA) | Rich, tamper-evident provenance while the file stays intact |
| **Imperceptible watermark** | Survives copy-paste / some transforms when metadata is stripped |
| **Visible labels / icons** | Human disclosure (deployers; does not alone meet machine-readable duties) |

**Free-form text** often relies mainly on a **generation-time watermark** — pure text cannot reliably carry file metadata. **Very short text** (roughly under ~200 tokens in many discussions of power/exemptions) is hard to mark or detect reliably and may be treated specially under guidance.

Major labs (Google with SynthID + C2PA, Anthropic with text watermark + C2PA, OpenAI with layered C2PA/SynthID-style approaches, Meta, and others) have aligned with EU transparency practice and are rolling methods out **globally**, not only for EU users. The landscape continues to evolve.

This is **not legal advice**. Provider terms of use may restrict intentional circumvention of *their* marks.

---

## Scope map (what cleantext hits)

| Category | Where the signal lives | Removed by cleantext? |
| --- | --- | --- |
| **Post-hoc Unicode / format stego** | Characters in the string (invisible, lookalike, spaces) | **Yes** |
| **Statistical / generative text watermarks** | Token choice during LLM decoding | **No** (needs rewrite) |
| **Metadata / C2PA provenance** | Signed manifests & EXIF/XMP in files | **No** |
| **Imperceptible media watermarks** | Image/video/audio signal itself | **No** |
| **Visible labels / icons** | UI overlays, disclaimers, EU icons | **No** (not text artifacts) |
| **Stylometry / classifiers** | Style features, not a keyed mark | **No** |
| **Fingerprints / internal logs** | Perceptual hashes; provider-side records | **No** |

---

## 1. Statistical / generative watermarks for text (LLM outputs)

These embed a detectable signal **during generation** by biasing token selection, with little or no visible quality loss. They **travel with plain copied text** — no special file format required.

### 1.1 Green–red list / soft watermark (Kirchenbauer et al.)

- **Paper:** Kirchenbauer et al., *A Watermark for Large Language Models* ([arXiv:2301.10226](https://arxiv.org/abs/2301.10226)) and many variants.
- **Mechanism:** A secret key + hash of prior context partitions the vocabulary into “green” and “red” lists. The model slightly boosts logits for green tokens.
- **Detection:** Statistical test (e.g. z-score) on the proportion of green tokens in a long enough passage.
- **Notes:** Early and widely studied; foundation for much follow-on work.

### 1.2 SynthID-Text (Google DeepMind)

- Uses **tournament sampling** — multiple layers of pseudorandom scoring of candidate tokens.
- Supports modes that better preserve output quality (including non-distortionary trade-offs discussed in research).
- Open-sourced components appear in ecosystems such as Hugging Face Transformers; used in production systems (e.g. Gemini).
- **Detection:** Probabilistic (watermarked / not / uncertain), not a character scrub.

### 1.3 Other sampling-based schemes

Research and prototypes aiming at better quality–robustness trade-offs or distortion-free properties (preserving more of the original token distribution), including:

- Gumbel-max style schemes (e.g. Aaronson / Kirchner lines of work)
- Unigram watermarks
- DiPMark and related methods

### 1.4 Company implementations (e.g. Anthropic Claude)

- Anthropic weaves an **imperceptible** watermark into Claude-generated text at the **model level**.
- Survives copy-paste; **may persist through some editing**.
- Exact algorithm details are **not public**; treat as this statistical class.
- A positive detection typically means content *may have been processed* by that system (including proofreading or summarizing human text) — not a cryptographic proof of sole AI authorship. **Absence of a mark proves nothing.**

### Strengths and limitations (text statistical marks)

| Strengths | Limitations |
| --- | --- |
| Survives plain-text paste | Weak on **short** or **low-entropy** text |
| No extra container format | Vulnerable to **heavy paraphrasing**, back-translation, structural rewrite |
| Machine-detectable in long passages | Residual n-grams can leak signal after **light** edits on long docs |

### What degrades statistical text marks

| Approach | Notes |
| --- | --- |
| **Heavy paraphrase / rewrite** with a *different* model or human | Strongest practical attack; multi-pass stronger |
| **Back-translation** (e.g. EN→other→EN) | Often effective; quality varies |
| **Outline → regenerate** | Extract key points; expand with another model |
| **Code:** format + rename + light refactor, or equivalent rewrite | Code is lower entropy; pure sampling marks are often weaker, but patterns remain |

**Do not** paraphrase with the *same marked model* if the goal is to remove *its* mark — it may re-apply one.

**`cleantext` does not implement paraphrasing.** See `cleantext --limitations`.

---

## 2. Metadata and cryptographic provenance

These attach structured, often **signed** information rather than (or in addition to) altering the content bits.

### 2.1 C2PA Content Credentials

- Industry open standard from the **Coalition for Content Provenance and Authenticity**.
- Cryptographically signed manifests can record creator, tools, AI involvement, timestamps, and edit history; **tamper-evident** when the binding holds.
- Widely adopted for images, video, and supported files (PNG, JPG, SVG, and others) by vendors such as Google, OpenAI, Anthropic, Adobe, and others.

### 2.2 Simpler tags and signatures

- EXIF, XMP, IPTC fields; “Made with AI” style labels.
- Cryptographic signatures or content hashes for authenticity.

| Strengths | Limitations |
| --- | --- |
| Rich provenance detail | Easily stripped by re-save, screenshot, conversion, many social uploads |
| Strong while the file stays intact | **Not suitable** for pure free-form text |

**Out of scope for cleantext.** Use metadata tools (`exiftool -all=`, re-encode/re-save) for files.

---

## 3. Invisible content-level watermarks (images, video, audio)

These modify the **signal itself** below typical human perception — a different channel from text token bias or C2PA.

### 3.1 SynthID (Google DeepMind) and peers

- **Images / video:** Subtle changes (often frequency-domain or distributed across pixels/frames) applied during generation. Aimed at surviving compression, cropping, filters, screenshots, and some transforms. Neural detectors identify the mark.
- **Audio:** Inaudible patterns with analogous goals.
- Deployed across Google tools and partnered with others for certain modalities.
- Research alternatives include Stable Signature, Tree-Ring, frequency-domain and diffusion-model-based schemes.

| Strengths | Limitations |
| --- | --- |
| More robust to common edits than pure metadata | Strong regeneration (e.g. diffusion re-render), aggressive filtering, or specialized attacks can degrade marks |
| Works after metadata is gone | Quality vs. robustness trade-offs at higher strength |

**Out of scope for cleantext** (not a media pipeline).

---

## 4. Visible / human-readable labels and icons

Required primarily for **deployers** (not only foundation-model providers) in specific cases:

- Overlays, logos, or text disclaimers (e.g. product “sparkle” icons, platform “AI-generated” badges).
- Official **EU icons** (e.g. black/white variants) for deepfakes and certain AI-generated public-interest text — meant to be clearly perceivable at first exposure and ideally remain visible on re-shares.
- Chatbots must **self-identify** as AI.

These satisfy **human disclosure** rules. They do **not alone** meet the **machine-readable** marking obligation expected of providers for generative outputs.

**Out of scope for cleantext.**

---

## 5. Post-hoc Unicode / format steganography (what cleantext targets)

Applied **after** generation (or by third-party tools): synonym games, syntactic tweaks, or — most relevant here — **invisible Unicode**, alternate spaces, homoglyphs, and trailing whitespace. Weaker and sometimes more noticeable than generation-time statistical marks; still used in research and some tooling.

### 5.1 Invisible and zero-width characters

| Characters (examples) | Role |
| --- | --- |
| U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ | Classic bit carriers (e.g. StegCloak) |
| U+2060 word joiner, U+FEFF BOM/ZWNBSP | Invisible separators |
| U+00AD soft hyphen | Often invisible unless line-break rules apply |
| U+200E–U+200F, U+202A–U+202E, U+2066–U+2069 | Bidi / directional controls |
| U+FE00–U+FE0F, U+E0100–U+E01EF | Variation selectors |
| U+E0000–U+E007F | Tags block (rarely legitimate in prose) |

**Research / tools:** StegCloak, AITSteg, CovertSYS-style embeddings.

**Countermeasure:** Strip the set; optional aggressive strip of residual category `Cf`. **`cleantext` does this.**

### 5.2 Alternate whitespace

| Characters (examples) | Notes |
| --- | --- |
| U+00A0 NBSP, U+202F narrow NBSP | Visually space-like |
| U+2000–U+200A | En/em/thin/hair/three-per-em, … |
| U+3000 ideographic space | Wide space |
| U+2800 braille blank | Sometimes abused as a “space” |

**Research / tools:** Innamark, UniSpaCh, Rizzo (space variants).

**Countermeasure:** Map → ASCII space. **`cleantext` does this.**

### 5.3 Homoglyph / confusable substitution

| Source | Examples |
| --- | --- |
| Cyrillic | а→a, о→o, р→p, с→c, е→e, … |
| Greek | ο→o, Α→A, … |
| Fullwidth Latin | ａ→a, Ａ→A |
| Math / letterlike symbols | ℂ, ℕ, ℝ → C, N, R |

**Research / tools:** LookALikes, Rizzo; Unicode confusables ([UTR #39](https://unicode.org/reports/tr39/)).

**Countermeasure:** Map known confusables to ASCII Latin (practical subset). **`cleantext` does this.**

### 5.4 Trailing whitespace (SNOW-style)

Encode bits in trailing spaces/tabs at end of lines.

**Countermeasure:** Strip trailing spaces/tabs per line. **`cleantext` does this** unless `--keep-trailing-ws`.

### 5.5 Punctuation and special apostrophes

Smart quotes, en/em dashes, modifier-letter apostrophes (e.g. U+2019, U+02BC, U+02B9) as marks or stego alphabet.

**Countermeasure:** Normalize to ASCII `'` / `"` / `-`. **`cleantext` does this** unless `--no-punct`.

---

## 6. Supplementary and emerging methods

| Method | Notes |
| --- | --- |
| **Fingerprinting / perceptual hashing** | Content-derived IDs for matching or tracking — not the same as a generative watermark |
| **Internal logging** | Provider-side records; not readable from the public output alone |
| **Model- or training-data watermarks** | More about ownership / dataset claims than wild detection of a single paste |
| **Code-specific patterns** | Often treated like text (sampling bias); sometimes comments, layout, or structural habits. Low-entropy code is harder to mark robustly |

---

## 7. Detection “in the wild” — practical reality

- Providers are expected to offer **detection mechanisms** (some free/public) and to move toward **interoperability** over time (industry codes discuss multi-year milestones).
- **Multi-layer** signals (C2PA + statistical text watermark + media SynthID-style marks) improve detection odds when several layers remain.
- Research consistently shows determined attacks can **significantly degrade or remove** many marks:
  - **Text:** heavy paraphrase / rewrite
  - **Media:** diffusion-style regeneration, aggressive filtering
  - **Metadata:** strip / re-encode / social re-upload
- **Absence of a detected mark ≠ human origin.**  
  **Presence of a mark ≠ sole AI authorship** (processing human text can leave a mark).

---

## 8. Practical workflow for text and code

For content you control:

1. **Unicode / format layer** — run **`cleantext`** (this project).  
2. **Statistical generation layer** — substantial rewrite with a *non-marked or different* model, or by hand.  
3. **Files** — strip C2PA / EXIF / XMP (and consider re-encoding) for media; media *signal* watermarks need separate approaches outside this repo.

### Reality check for this tool

| Method family | `cleantext` action |
| --- | --- |
| Zero-width / invisible / bidi / VS / Tags | Strip |
| Alternate spaces | Normalize to U+0020 |
| Homoglyphs (common set) | Map to ASCII Latin |
| Trailing WS payloads | Strip (default) |
| Fancy punctuation / special apostrophes | Normalize to ASCII (default) |
| NFKC | Optional (default on) |
| Kirchenbauer / SynthID-Text / Claude-class sampling | **Not handled** |
| C2PA / EXIF / media SynthID | **Not handled** |
| Visible labels, stylometry, fingerprints | **Not handled** |

In-CLI summary:

```bash
cleantext --limitations
```

---

## References (starting points)

- EU AI Act transparency obligations for generative systems (Article 50 and implementing / Code of Practice materials)
- Kirchenbauer et al., *A Watermark for Large Language Models*, [arXiv:2301.10226](https://arxiv.org/abs/2301.10226)
- Google DeepMind materials on **SynthID** / **SynthID-Text**
- C2PA specifications for content credentials / manifests
- Unicode Consortium, [UTR #39 Unicode Security Mechanisms](https://unicode.org/reports/tr39/) (confusables)
- Historical / academic text stego: StegCloak, SNOW, Innamark, UniSpaCh, LookALikes, Rizzo, AITSteg, …

This document is informational. Production systems, detectors, and guidance change; treat details as **time-sensitive** (context as of ~2026).

# PICOS Community Edition — text normalization + output guards
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
Defense-in-depth guards around the machine-translation step.

Offline MT (Argos/CTranslate2) can *degenerate* on short, out-of-distribution
input — decoding an unbounded repetition such as "mainstremainstremainstre…"
instead of a translation. This was observed live on the reference machine for
ES->EN on single words. The degeneration is environment-sensitive (it did not
reproduce on every CPU build), so rather than rely on a single upstream fix we:

  * normalize ASR text before it reaches the glossary/MT (so trailing
    punctuation and casing don't block a glossary match), and
  * reject MT output that is implausibly long or visibly repetitive, returning
    a clear failure string that is NEVER spoken aloud.

Everything here is pure-Python string work: no models, no network, fast to test.
"""
from __future__ import annotations

import re

# Shown (and returned) instead of a degenerate/implausible machine translation.
# The pipeline treats this as a sentinel and never sends it to TTS.
TRANSLATION_FAILED = "(translation failed — try again)"

# Punctuation stripped from the ends of ASR text (keeps internal punctuation).
_TERMINAL_PUNCT = " \t\r\n.,;:!?¿¡…\"'“”‘’«»()[]{}-–—"


def normalize_asr(text: str) -> str:
    """
    Canonicalize recognized/typed text before glossary lookup and MT.

    Collapses internal whitespace, strips leading/trailing punctuation, and
    case-folds. ASR routinely returns capitalized, period-terminated phrases
    ("De mandado.") that would otherwise never match a lowercase glossary term;
    normalizing first gives them a chance. The result is also what we hand to
    the translator — lowercase, punctuation-trimmed input is friendlier to the
    MT model than a lone capitalized token.
    """
    if not text:
        return ""
    text = " ".join(text.split())          # collapse internal whitespace
    text = text.strip(_TERMINAL_PUNCT)      # drop wrapping punctuation
    return text.casefold().strip()


def looks_degenerate(text: str) -> bool:
    """
    True if `text` shows the repetition signature of a degenerate decode.

    Catches three shapes:
      1. a chunk of >=2 characters repeated back-to-back 4+ times
         ("mainstremainstremainstremainstre"),
      2. a single character repeated 8+ times ("aaaaaaaa"),
      3. word-level repetition — the same word 5+ times running, or very low
         token diversity across a long-ish output.
    Short, ordinary output (a word or a sentence) is never flagged.
    """
    t = (text or "").strip()
    if len(t) < 8:
        return False

    compact = re.sub(r"\s+", "", t).casefold()
    # 1) a 2–20 char unit repeated 4+ times in a row (3 extra reps after the 1st)
    if re.search(r"(.{2,20}?)\1{3,}", compact):
        return True
    # 2) one character run of 8+
    if re.search(r"(.)\1{7,}", compact):
        return True

    # 3) token-level repetition / low diversity
    words = t.casefold().split()
    if len(words) >= 6:
        run = 1
        for a, b in zip(words, words[1:]):
            run = run + 1 if a == b else 1
            if run >= 5:
                return True
        if len(set(words)) / len(words) <= 0.3:
            return True
    return False


def is_suspicious_translation(source: str, translation: str,
                              max_ratio: float = 4.0, floor: int = 40) -> bool:
    """
    True if `translation` should be rejected as an MT failure.

    Two independent checks, applied between MT and display/TTS:
      * length blow-up — output longer than `max_ratio`x the source (with a
        `floor` so short legitimate translations aren't punished), and
      * the repetition signature from `looks_degenerate`.
    An empty translation is *not* "suspicious" here (the pipeline handles empty
    input/no-speech separately); this only rejects positively-bad output.
    """
    out = (translation or "").strip()
    if not out:
        return False
    src = (source or "").strip()
    if len(out) > max(int(max_ratio * len(src)), floor):
        return True
    return looks_degenerate(out)

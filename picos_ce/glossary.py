# PICOS Community Edition — basic legal-glossary substitution
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
#
# NOTE: the glossary DATA (data/glossary_en_es_starter.csv) is not GPL — it is
# David F. Proano Celi's compilation, dedicated to the public domain (CC0 1.0
# Universal). See GLOSSARY-LICENSE.txt. This CODE that reads it is GPL like
# the rest.
"""
Basic glossary substitution.

The glossary is a flat CSV of English,Spanish[,Note] legal-term pairs. Before a
sentence is machine-translated, we do ONE conservative substitution: if a known
source-language term appears in the text, we replace that span with the exact
target-language term, so the machine translator preserves the correct legal
wording instead of paraphrasing it.

The two columns are mapped to language codes (default: English=en, Spanish=es)
so the substitution direction is chosen from the pipeline's from_lang. A glossary
for another language pair just needs different column languages — no code change.

This is intentionally simple (one best match, replace-once). There is no
per-context logic, no possessive handling, and no placeholder machinery — that
lives in the commercial edition.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, drop leading articles — for matching only."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text, flags=re.UNICODE)
    text = re.sub(r"\b(the|a|an)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class Entry:
    a: str        # term in language `lang_a` (default English)
    b: str        # term in language `lang_b` (default Spanish)
    note: str
    norm_a: str
    norm_b: str


class Glossary:
    """Loads a two-language term list and does conservative substitution."""

    def __init__(self, csv_path: str, lang_a: str = "en", lang_b: str = "es",
                 col_a: str = "English", col_b: str = "Spanish"):
        self.lang_a = lang_a
        self.lang_b = lang_b
        self.col_a = col_a
        self.col_b = col_b
        self.entries: list[Entry] = []
        self.load(csv_path)

    def load(self, csv_path: str) -> None:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                a = (row.get(self.col_a) or "").strip()
                b = (row.get(self.col_b) or "").strip()
                note = (row.get("Note") or "").strip()
                if a and b:
                    self.entries.append(Entry(a, b, note, normalize(a), normalize(b)))
        # match longer terms first so multi-word phrases win over their parts
        self.entries.sort(key=lambda e: len(e.norm_a), reverse=True)

    def __len__(self) -> int:
        return len(self.entries)

    def _sides(self, source_lang: str):
        """Return (norm_attr, needle_attr, repl_attr) for the source language,
        or None if this glossary doesn't cover that language."""
        if source_lang == self.lang_a:
            return ("norm_a", "a", "b")   # match a-side, replace a->b
        if source_lang == self.lang_b:
            return ("norm_b", "b", "a")   # match b-side, replace b->a
        return None

    def lookup(self, text: str, source_lang: str) -> str | None:
        """
        If the whole (normalized) input IS a known term in `source_lang`, return
        its exact equivalent; otherwise None.

        This lets the pipeline **short-circuit** machine translation in either
        direction: a phrase that is exactly a glossary term is translated by the
        glossary alone and never reaches the MT model. That both guarantees the
        correct legal wording and sidesteps MT degeneration on bare single-word
        input (see picos_ce/guards.py). Whole-term match only — partial/contained
        matches fall through to MT (via `apply`).
        """
        sides = self._sides(source_lang)
        if sides is None:
            return None
        norm_attr, _needle_attr, repl_attr = sides
        norm = normalize(text)
        if not norm:
            return None
        for e in self.entries:
            if norm == getattr(e, norm_attr):
                return getattr(e, repl_attr)
        return None

    def apply(self, text: str, source_lang: str) -> str:
        """
        Substitute one known term (in `source_lang`) with its equivalent, so the
        MT step passes the exact legal wording through. Conservative: at most one
        replacement, case-insensitive, once. No-op if the glossary doesn't cover
        `source_lang`.
        """
        if not text.strip():
            return text
        sides = self._sides(source_lang)
        if sides is None:
            return text
        norm_attr, needle_attr, repl_attr = sides
        norm = normalize(text)
        # exact-normalized match first, then contained-phrase match
        match = None
        for e in self.entries:
            if norm == getattr(e, norm_attr):
                match = e
                break
        if match is None:
            # contained *whole-word* phrase match — pad with spaces so a term
            # only matches on token boundaries. Without this, "demanda"
            # (complaint) matched *inside* "demandado" and corrupted it to
            # "complaintdo" before MT — a root cause of the ES->EN failure.
            padded = f" {norm} "
            for e in self.entries:
                term = getattr(e, norm_attr)
                if term and f" {term} " in padded:
                    match = e
                    break
        if match is None:
            return text
        needle = getattr(match, needle_attr)
        repl = getattr(match, repl_attr)
        if needle and needle.lower() in text.lower():
            return _replace_once_ci(text, needle, repl)
        return text


def _replace_once_ci(src: str, needle: str, repl: str) -> str:
    # Word-boundary anchored so a term is only replaced as a whole word, never
    # as a substring of a longer word (guards against "demandado" -> partial hit).
    pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", re.IGNORECASE)
    return pattern.sub(repl, src, count=1)

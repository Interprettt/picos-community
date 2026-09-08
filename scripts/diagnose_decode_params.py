#!/usr/bin/env python3
# PICOS Community Edition — diagnostic tool, not part of the product.
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Sweep CTranslate2's compute_type (and, secondarily, its decode search
parameters) to check for the field-reported ES->EN degeneration
("mainstremainstremainstre...@@").

CONFIRMED ROOT CAUSE (see picos_ce/translate.py's _force_float32_compute_type()
docstring for the full trail, including two earlier theories tested and
ruled out): argostranslate asks CTranslate2 for compute_type="auto", which
CTranslate2 resolves per-CPU to the fastest supported type. On at least one
affected machine (AMD x86) that resolves to int8, and the es->en model
degenerates under int8 there -- same package, same tokens, float32 and the
library's own un-configured default both correct, int8 alone garbage. This
branch now forces float32 by default (see README); this script exists to
reproduce that A/B/C proof directly on any machine, and as a general tool if
a *different* compute_type/model/CPU combination ever shows the same shape
of bug.

An earlier version of this script only swept beam_size/length_penalty/
no_repeat_ngram_size and never varied compute_type at all -- it silently
rode CTranslate2's own un-configured default for every configuration, which
is why it reported "all clean" on hardware that (with argostranslate's real
compute_type="auto") was not clean. Lesson: when isolating a variable,
actually vary the suspect axis.

Usage (after ./scripts/setup_models.sh has installed the es<->en packages):
    python3 scripts/diagnose_decode_params.py "demandado"
    python3 scripts/diagnose_decode_params.py "el acusado tiene derecho a un abogado"

Prints one line per compute_type x decode-params combination. Whichever
compute_type(s) degenerate on THIS machine pin the actual trigger.
"""
from __future__ import annotations

import re
import sys

import argostranslate.package as pkg
import ctranslate2


def get_es_en_package():
    for p in pkg.get_installed_packages():
        if p.from_code == "es" and p.to_code == "en":
            return p
    sys.exit(
        "ERROR: es->en Argos package not installed.\n"
        "Run:  ./scripts/setup_models.sh es:en"
    )


# The primary axis: compute_type. "auto" is what argostranslate actually
# requests by default (ARGOS_COMPUTE_TYPE env var, default "auto") -- that's
# the one that matters most. The rest are CTranslate2's other named types;
# get_supported_compute_types('cpu') below reports which ones this specific
# machine can even run.
COMPUTE_TYPES_TO_TRY = ["auto", "float32", "int8", "int8_float32", "float16"]

# Secondary axis: decode search parameters. Kept from the earlier round of
# this script -- beam search vs. greedy, with/without a repetition guard --
# in case a future report implicates decode parameters on top of, or
# instead of, compute_type.
DECODE_CONFIGS = [
    ("greedy (beam_size=1)", dict(beam_size=1)),
    ("argostranslate's real params", dict(beam_size=4, length_penalty=0.2, num_hypotheses=4)),
]


def looks_degenerate(text: str) -> bool:
    t = text.strip()
    if len(t) < 8:
        return False
    compact = re.sub(r"\s+", "", t).casefold()
    return bool(re.search(r"(.{2,20}?)\1{3,}", compact)) or "@@" in text


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {sys.argv[0]} 'text to translate (Spanish)'")
    text = sys.argv[1]

    p = get_es_en_package()
    model_path = str(p.package_path / "model")
    print(f"Package: {p.package_path}")
    print(f"Input:   {text!r}")
    print(f"CPU-supported compute types here: {sorted(ctranslate2.get_supported_compute_types('cpu'))}\n")

    tokens = p.tokenizer.encode(text)
    print(f"Tokens (argostranslate's own tokenizer): {tokens}\n")

    any_bad = False
    for compute_type in COMPUTE_TYPES_TO_TRY:
        try:
            translator = ctranslate2.Translator(model_path, compute_type=compute_type)
        except Exception as e:  # noqa: BLE001 - diagnostic tool, show everything
            print(f"[compute_type={compute_type}] <could not construct: {type(e).__name__}: {e}>\n")
            continue
        for label, kwargs in DECODE_CONFIGS:
            try:
                result = translator.translate_batch([tokens], **kwargs)
                out = p.tokenizer.decode(result[0].hypotheses[0])
            except Exception as e:  # noqa: BLE001
                out = f"<EXCEPTION: {type(e).__name__}: {e}>"
            bad = looks_degenerate(out)
            any_bad = any_bad or bad
            flag = "  <-- DEGENERATE" if bad else ""
            print(f"[compute_type={compute_type:<14} | {label}]")
            print(f"  output: {out!r}{flag}\n")

    if any_bad:
        print("=> At least one compute_type degenerated. That pins the actual trigger --")
        print("   PICOS forces float32 by default; if float32 itself is clean above,")
        print("   this branch's fix already covers this machine.")
    else:
        print("=> Nothing degenerated on this machine/input. If you still see the bug")
        print("   through `python -m picos_ce`, try a longer/more unusual input, or")
        print("   open an issue with this script's full output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

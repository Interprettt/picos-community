# PICOS Community Edition — command-line interface
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
CLI entry point.  Run:

    python -m picos_ce --from en                 # interactive mic loop, EN->ES
    python -m picos_ce --from es                 # interactive mic loop, ES->EN
    python -m picos_ce --from en --to es          # explicit pair
    python -m picos_ce --from en --text "bail"   # one-shot, no microphone
    python -m picos_ce --from en --no-tts         # don't speak the result
    python -m picos_ce --from en --model base     # smaller model for low-RAM

The language pair (--from/--to) is passed as ISO codes and plumbed through the
whole pipeline. Version 0.1 ships English <-> Spanish; other pairs become
possible by installing their Argos packages and voices (no code change).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, tts
from . import translate as mt
from .pipeline import Pipeline

DEFAULT_GLOSSARY = Path(__file__).resolve().parent.parent / "data" / "glossary_en_es_starter.csv"

# languages the v0.1 release is documented/tested for. Widen this list (and add
# voices + Argos packages) to support more pairs — nothing else needs to change.
SUPPORTED_LANGS = ["en", "es"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="picos_ce",
        description="PICOS Community Edition — offline legal speech translation.",
    )
    p.add_argument("--from", "-f", dest="from_lang", choices=SUPPORTED_LANGS, default="en",
                   help="language you speak (ISO code). Default: en")
    p.add_argument("--to", "-o", dest="to_lang", choices=SUPPORTED_LANGS, default=None,
                   help="target language (ISO code). Default: the other supported language")
    p.add_argument("--model", "-m", default="small",
                   choices=["tiny", "base", "small", "medium", "large-v3"],
                   help="faster-whisper model size. Default: small (use base/tiny for low-RAM)")
    p.add_argument("--text", "-t", default=None,
                   help="translate this text once and exit (no microphone)")
    p.add_argument("--glossary", "-g", default=str(DEFAULT_GLOSSARY),
                   help="path to the glossary CSV (English,Spanish[,Note])")
    p.add_argument("--no-tts", dest="tts", action="store_false",
                   help="do not speak the result out loud")
    p.add_argument("--version", "-V", action="version", version=f"PICOS CE {__version__}")
    return p


def _resolve_pair(from_lang: str, to_lang: str | None) -> tuple[str, str]:
    """Infer the target language if omitted: the other supported language."""
    if to_lang is None:
        others = [l for l in SUPPORTED_LANGS if l != from_lang]
        to_lang = others[0] if others else from_lang
    return from_lang, to_lang


def main(argv: list[str] | None = None) -> int:
    """Parse args and run; turn Ctrl-C into a clean exit (no traceback)."""
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except KeyboardInterrupt:
        # Covers one-shot text mode, model loading, and package checks — the
        # interactive loop also handles Ctrl-C itself for a friendlier message.
        print("\nbye.")
        return 130


def _run(args: argparse.Namespace) -> int:
    from_lang, to_lang = _resolve_pair(args.from_lang, args.to_lang)
    if from_lang == to_lang:
        print("ERROR: --from and --to must be different languages.", file=sys.stderr)
        return 2

    # fail fast + friendly if the Argos language pack is missing
    try:
        mt.ensure_available(from_lang, to_lang)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    glossary_path = args.glossary if Path(args.glossary).exists() else None
    pipe = Pipeline(
        from_lang=from_lang,
        to_lang=to_lang,
        model_size=args.model,
        glossary_path=glossary_path,
        speak_result=args.tts,
    )

    gloss_n = len(pipe.glossary) if pipe.glossary else 0
    print(f"PICOS Community Edition v{__version__} — offline legal speech translation")
    print(f"Direction: {from_lang.upper()} -> {to_lang.upper()}   |   Model: {args.model}"
          f"   |   TTS: {tts.available() if args.tts else 'off'}   |   Glossary: {gloss_n} terms")

    # one-shot text mode
    if args.text is not None:
        pipe.run_text(args.text)
        return 0

    # interactive microphone loop
    print("\nPress ENTER to start recording, speak, then ENTER again to stop. "
          "Ctrl-C to quit.")
    while True:
        try:
            input("\n▶ ENTER to record ")
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return 0
        print("  ● recording... press ENTER to stop")
        try:
            pipe.run_mic()
        except KeyboardInterrupt:
            print("\nbye.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())

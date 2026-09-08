# PICOS Community Edition — pipeline orchestration
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
Ties the four stages together:

    transcribe (asr) -> glossary substitution -> translate (Argos) -> speak (tts)

The language pair is carried as (from_lang, to_lang) ISO codes throughout, so
the pipeline is not tied to any particular pair. `translate_text()` is the pure
text path (no mic, no audio) — the easy entry point for testing and `--text`.
"""
from __future__ import annotations

from . import asr, tts
from . import translate as mt
from .glossary import Glossary
from .guards import TRANSLATION_FAILED, is_suspicious_translation, normalize_asr


class Pipeline:
    def __init__(
        self,
        from_lang: str = mt.DEFAULT_FROM,
        to_lang: str = mt.DEFAULT_TO,
        model_size: str = "small",
        glossary_path: str | None = None,
        speak_result: bool = True,
    ):
        self.from_lang = from_lang
        self.to_lang = to_lang
        self.model_size = model_size
        self.speak_result = speak_result
        self.glossary = Glossary(glossary_path) if glossary_path else None
        self._model = None  # lazy: only load Whisper when the mic path is used

    # ---- text path (no microphone) ----

    def translate_text(self, text: str) -> str:
        """
        Normalize -> glossary (short-circuit or substitute) -> Argos MT -> guard.

        Order of operations (both directions):
          1. normalize the input (case-fold, strip terminal punctuation);
          2. if the whole phrase IS a glossary term, return its equivalent and
             DO NOT call MT (short-circuit — see glossary.lookup / guards.py);
          3. otherwise substitute any known term to steer MT, translate, and
          4. reject implausible/degenerate MT output as TRANSLATION_FAILED.
        """
        cleaned = normalize_asr(text)
        if not cleaned:
            return ""
        if self.glossary is not None:
            hit = self.glossary.lookup(cleaned, self.from_lang)
            if hit is not None:
                return hit
            source = self.glossary.apply(cleaned, self.from_lang)
        else:
            source = cleaned
        raw = mt.translate(source, self.from_lang, self.to_lang)
        if is_suspicious_translation(source, raw):
            return TRANSLATION_FAILED
        return raw

    def run_text(self, text: str) -> str:
        """Translate `text`, print it, and (optionally) speak it."""
        translation = self.translate_text(text)
        print(f"  {text}")
        print(f"  -> {translation}")
        if self.speak_result and translation and translation != TRANSLATION_FAILED:
            tts.speak(translation, self.to_lang)
        return translation

    # ---- microphone path ----

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        if asr.model_is_cached(self.model_size):
            print(f"  [asr] loading faster-whisper '{self.model_size}' model (offline) ...")
            self._model = asr.load_model(self.model_size)
        else:
            # First run: the only sanctioned network moment. Confirm explicitly.
            if not self._confirm_whisper_download():
                return None
            print(f"  [asr] downloading '{self.model_size}' model (one-time) ...")
            self._model = asr.load_model(self.model_size, allow_download=True)
        return self._model

    def _confirm_whisper_download(self) -> bool:
        """Show the model source + license and ask before the one-time download."""
        repo = asr.whisper_repo(self.model_size)
        print("\n  [asr] The Whisper speech model is not downloaded yet.")
        print(f"        Model:   {repo}")
        print(f"        Source:  Hugging Face — https://huggingface.co/{repo}")
        print("        License: MIT (OpenAI Whisper weights, CTranslate2-converted).")
        print("        This one-time fetch is the only time PICOS uses the network.")
        try:
            ans = input("        Download it now? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print()
            ans = ""
        if ans.strip().lower() in ("y", "yes"):
            return True
        print("  [asr] Skipped. Run  ./scripts/setup_models.sh --whisper  when ready.")
        return False

    def run_mic(self) -> str:
        """Record one phrase, transcribe, translate, speak. Returns translation."""
        model = self._ensure_model()
        if model is None:
            print("  [asr] no speech model available — nothing to transcribe.")
            return ""
        audio = asr.record_phrase()
        heard = asr.transcribe(model, audio, self.from_lang)
        if not heard:
            print("  [asr] (nothing recognized)")
            return ""
        translation = self.translate_text(heard)
        print(f"  heard: {heard}")
        print(f"  ->     {translation}")
        if self.speak_result and translation and translation != TRANSLATION_FAILED:
            tts.speak(translation, self.to_lang)
        return translation

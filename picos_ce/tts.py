# PICOS Community Edition — text-to-speech (Piper, espeak-ng fallback)
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
Speak translated text out loud.

Preferred engine: Piper (neural, natural). Fallback: espeak-ng (robotic but
tiny and always available). If neither is present, we print a hint and stay
silent — never crash.

Voice selection is by language code, so it is not tied to any single pair.
Voices are NOT bundled. scripts/setup_models.sh downloads Piper voices to
  ~/.local/share/picos-community/piper/
Override discovery with environment variables (LANG is the upper-case code):
  PICOS_PIPER_BIN            path to the piper binary
  PICOS_PIPER_VOICE_<LANG>   path to a *.onnx voice, e.g. PICOS_PIPER_VOICE_ES
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

DATA_DIR = Path(os.environ.get("PICOS_CE_HOME", Path.home() / ".local/share/picos-community"))
PIPER_DIR = DATA_DIR / "piper"


def _piper_bin() -> str | None:
    return os.environ.get("PICOS_PIPER_BIN") or shutil.which("piper")


def _piper_voice(lang: str) -> str | None:
    env = os.environ.get(f"PICOS_PIPER_VOICE_{lang.upper()}")
    if env and Path(env).exists():
        return env
    # else: first *.onnx whose filename starts with the language code
    for base in (PIPER_DIR, PIPER_DIR / "models"):
        if base.is_dir():
            for onnx in sorted(base.glob("*.onnx")):
                if onnx.name.lower().startswith(lang.lower()):
                    return str(onnx)
    return None


def _play_wav(path: str) -> None:
    """Play a WAV file through the default output device via sounddevice."""
    import numpy as np
    import sounddevice as sd

    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    audio = np.frombuffer(frames, dtype="int16")
    sd.play(audio, rate)
    sd.wait()


def _speak_piper(text: str, lang: str) -> bool:
    binp = _piper_bin()
    voice = _piper_voice(lang)
    if not binp or not voice:
        return False
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        out = tf.name
    try:
        # --output_file works across piper builds (pip piper-tts and the
        # community arm build); text is read from stdin.
        proc = subprocess.run(
            [binp, "--model", voice, "--output_file", out],
            input=text.encode("utf-8"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if proc.returncode != 0 or not os.path.getsize(out):
            return False
        _play_wav(out)
        return True
    except Exception:
        return False
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


# map ISO codes to espeak-ng voice names where they differ; default to the code
_ESPEAK_VOICE = {"en": "en-us", "es": "es"}

# one-time hint when we fall back to espeak-ng, so the user knows why speech is
# robotic and how to get natural Piper voices (see item 5f runtime resolution).
_espeak_hint_shown = False


def _speak_espeak(text: str, lang: str) -> bool:
    global _espeak_hint_shown
    binp = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binp:
        return False
    if not _espeak_hint_shown:
        print("  [tts] using espeak-ng fallback (robotic). Install a Piper voice "
              "for natural speech — see README / scripts/setup_models.sh --voice.")
        _espeak_hint_shown = True
    voice = _ESPEAK_VOICE.get(lang, lang)
    try:
        subprocess.run(
            [binp, "-v", voice, text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        return False


def available() -> str:
    """Report which TTS engine would be used: 'piper', 'espeak', or 'none'."""
    if _piper_bin() and (_piper_voice("en") or _piper_voice("es")):
        return "piper"
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return "espeak"
    return "none"


def speak(text: str, lang: str) -> bool:
    """Speak `text` in `lang` ('en'/'es'). Returns True if audio was produced."""
    text = (text or "").strip()
    if not text:
        return False
    if _speak_piper(text, lang):
        return True
    if _speak_espeak(text, lang):
        return True
    print("  [tts] No Piper voice or espeak-ng found — install one to hear output "
          "(see README / scripts/setup_models.sh).")
    return False

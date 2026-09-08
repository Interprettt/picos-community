# PICOS Community Edition — speech recognition (faster-whisper) + mic capture
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
On-device speech recognition with faster-whisper, plus simple push-to-record
microphone capture via sounddevice.

OFFLINE GUARANTEE
-----------------
The Whisper model is fetched from Hugging Face exactly ONCE, and only through a
sanctioned path (``setup_models.sh --whisper`` or an explicit interactive
confirmation). After that:

  * if the model is already cached, ``load_model`` constructs the model with
    ``local_files_only=True`` and sets ``HF_HUB_OFFLINE=1`` for the whole
    process, so the runtime never contacts Hugging Face again; and
  * if the model is NOT cached and download was not sanctioned, ``load_model``
    raises a clear "run setup" error instead of silently reaching out or dumping
    a raw huggingface_hub traceback.

Everything else in this module (mic capture, transcription) is fully local.
"""
from __future__ import annotations

import os

SAMPLE_RATE = 16000  # what Whisper expects
CHANNELS = 1


def whisper_repo(size: str) -> str:
    """Hugging Face repo id backing a faster-whisper size name (best effort)."""
    try:
        from faster_whisper.utils import _MODELS  # size -> repo id
        if size in _MODELS:
            return _MODELS[size]
    except Exception:  # pragma: no cover - version guard
        pass
    # The sizes the CLI offers all follow this pattern.
    return f"Systran/faster-whisper-{size}"


def _force_hf_offline() -> None:
    """Lock this process out of Hugging Face network calls (belt & suspenders)."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    try:  # honour it even though huggingface_hub read the env at import time
        import huggingface_hub.constants as _c
        _c.HF_HUB_OFFLINE = True
    except Exception:  # pragma: no cover - version guard
        pass


def model_is_cached(size: str = "small", download_root: str | None = None) -> bool:
    """
    True if the Whisper model is already available locally (no network needed).

    A filesystem path counts as local; otherwise we ask huggingface_hub whether
    the repo snapshot is fully in the cache using ``local_files_only=True``,
    which never touches the network.
    """
    if os.path.isdir(size):
        return True
    try:
        from huggingface_hub import snapshot_download
    except ImportError:  # pragma: no cover - environment guard
        return False
    try:
        snapshot_download(whisper_repo(size), local_files_only=True,
                          cache_dir=download_root)
        return True
    except Exception:
        return False


def load_model(size: str = "small", device: str = "cpu", compute_type: str = "int8",
               download_root: str | None = None, allow_download: bool = False):
    """
    Load a faster-whisper model, offline-first. `size` in
    {tiny, base, small, medium, large-v3} or a local model directory.

    * cached  -> construct with local_files_only=True and lock the process
      offline (HF_HUB_OFFLINE=1). No network.
    * not cached + allow_download=True -> the one sanctioned first-run download.
    * not cached + allow_download=False -> raise a friendly "run setup" error
      (never a raw huggingface_hub traceback).
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover - environment guard
        raise RuntimeError(
            "faster-whisper is not installed. Run: pip install -r requirements.txt"
        ) from e

    if model_is_cached(size, download_root):
        _force_hf_offline()
        return WhisperModel(size, device=device, compute_type=compute_type,
                            download_root=download_root, local_files_only=True)

    if allow_download:
        # The ONLY sanctioned network moment (setup --whisper, or confirmed live).
        return WhisperModel(size, device=device, compute_type=compute_type,
                            download_root=download_root, local_files_only=False)

    raise RuntimeError(
        f"Whisper model '{size}' is not downloaded yet, so there is nothing to "
        f"load offline.\n"
        f"Fetch it once (it shows the model's source + license first):\n"
        f"    ./scripts/setup_models.sh --whisper --whisper-model {size}\n"
        f"or start a mic session and confirm the one-time download when prompted."
    )


def record_phrase():
    """
    Record a single phrase from the default microphone. Recording starts
    immediately and stops when the user presses Enter. Returns a float32 mono
    numpy array at SAMPLE_RATE, or None if nothing was captured.
    """
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError as e:  # pragma: no cover - environment guard
        raise RuntimeError(
            "numpy/sounddevice are not installed. Run: pip install -r requirements.txt"
        ) from e

    frames: list = []

    def callback(indata, _frames, _time, status):
        if status:
            # over/underflows are non-fatal; keep going
            pass
        frames.append(indata.copy())

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", callback=callback
    ):
        try:
            input()  # block until Enter; audio accumulates in the callback
        except (EOFError, KeyboardInterrupt):
            pass

    if not frames:
        return None
    return np.concatenate(frames, axis=0).flatten()


def transcribe(model, audio, lang: str) -> str:
    """Transcribe a float32 mono 16 kHz array in the given language ('en'/'es')."""
    if audio is None or len(audio) == 0:
        return ""
    segments, _info = model.transcribe(
        audio,
        language=lang,
        vad_filter=True,
        condition_on_previous_text=False,
        beam_size=1,
    )
    return " ".join(s.text.strip() for s in segments).strip()

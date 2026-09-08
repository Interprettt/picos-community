# Third-Party Notices — PICOS Community Edition

PICOS Community Edition depends on the following open-source components. None of
them are bundled in this repository — they are installed by `pip` (Python
dependencies) or downloaded by `scripts/setup_models.sh` (models and voices).
Each remains under its own license.

PICOS Community Edition's own source code is licensed under **GPL v3** (see
`LICENSE`). The starter glossary is public domain — **CC0 1.0 Universal** (see
`GLOSSARY-LICENSE.txt`).

---

## Speech recognition

### faster-whisper
- **License:** MIT — https://github.com/SYSTRAN/faster-whisper
- On-device automatic speech recognition (EN/ES). Installed via pip.

### CTranslate2
- **License:** MIT — https://github.com/OpenNMT/CTranslate2
- Inference engine used internally by faster-whisper. Installed via pip.

### OpenAI Whisper (model weights)
- **License:** MIT — https://github.com/openai/whisper
- The faster-whisper models derive from OpenAI Whisper weights. Auto-downloaded
  on first run and cached locally.

---

## Machine translation

### Argos Translate
- **License:** MIT — https://github.com/argosopentech/argos-translate
- Offline EN<->ES machine translation. Used via its public API, **no
  modifications**. Installed via pip.

### Argos EN<->ES language packages
- **License:** MIT (package tooling). The bundled model is derived from an
  OPUS-MT model licensed **CC-BY 4.0** (per the package's own README). The
  `.argosmodel` metadata does not embed a license field, so `setup_models.sh`
  reports this at install time and points to the Argos OpenTech package index —
  https://www.argosopentech.com/argospm/index/
- Downloaded by `scripts/setup_models.sh` only after showing this and asking.

### Stanza
- **License:** Apache License 2.0 — https://github.com/stanfordnlp/stanza
- Sentence-boundary detection / tokenization, used internally by Argos
  Translate for languages (including Spanish) that need it. **Not a direct
  PICOS dependency** — pulled in transitively by `argostranslate`, and not
  originally covered by this project's offline audit because of that (see
  the README's [Offline guarantee](README.md#offline-guarantee) section for
  what changed). Its tokenizer resource files are normalized once by
  `scripts/setup_models.sh` in the same sanctioned network window as the
  Argos package download; `picos_ce` then blocks any further network access
  to it at runtime.

---

## Audio & numerics

### numpy
- **License:** BSD 3-Clause — https://github.com/numpy/numpy
- Audio buffer processing. Installed via pip.

### sounddevice
- **License:** MIT — https://github.com/spatialaudio/python-sounddevice
- Microphone capture and playback via PortAudio. Installed via pip.

---

## Text-to-speech (optional, external)

### Piper (piper1-gpl)
- **License:** GPL v3 — https://github.com/OHF-Voice/piper1-gpl
- Preferred neural TTS engine. Installed separately / downloaded by
  `scripts/setup_models.sh`. Voice models carry their own (permissive) licenses;
  see each voice's `MODEL_CARD`.

### espeak-ng
- **License:** GPL v3 — https://github.com/espeak-ng/espeak-ng
- Fallback TTS engine. Installed from your distribution's package manager.

---

PICOS Community Edition itself is licensed under GPL v3. See `LICENSE`.

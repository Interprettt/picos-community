# PICOS Community Edition

**Offline English ⇄ Spanish legal-term speech translation, in about 1,050 lines of Python.**

![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue) ![Platform: Linux](https://img.shields.io/badge/Platform-Linux-informational) ![Interface: CLI](https://img.shields.io/badge/Interface-CLI-lightgrey)

You speak a legal term. It transcribes, translates, checks a glossary, and says the answer back. Everything runs on your machine.

```
  🎙  transcribe     →   🌐 translate    →   📘 glossary      →   🔊 speak
     faster-whisper       Argos Translate     substitution        Piper / espeak-ng
```

Built by a working court interpreter, opened up so you can read it, break it, and build on it.

---

## Try it

```
$ python -m picos_ce --from en --text "restraining order"
PICOS Community Edition v0.1.0 — offline legal speech translation
Direction: EN -> ES   |   Model: small   |   TTS: none   |   Glossary: 30 terms
  restraining order
  -> orden de restricción
```

---

## Setup

You need Linux, Python 3.9+, and about 2 GB of disk for the models. A GPU is not required.

**1. Get the code**

```bash
git clone https://github.com/Interprettt/picos-community.git
cd picos-community
```

Downloading the ZIP from GitHub instead? It extracts to `picos-community-main`.

**2. Make a virtual environment**

```bash
sudo apt install python3-venv        # Debian/Ubuntu/Mint, if you don't have it
python3 -m venv venv
source venv/bin/activate
```

Run `source venv/bin/activate` again in every new terminal.

**3. Install dependencies**

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

That first line matters: it grabs the CPU build of PyTorch. Skip it and pip pulls about a gigabyte of NVIDIA packages you won't use.

**4. Download the models**

```bash
./scripts/setup_models.sh
```

This shows you each thing it wants to download, with its license, and asks before fetching anything. See [Licensing](#licensing) below.

That's it. After this, PICOS never touches the network again.

---

## Using it

```bash
# Speak: press ENTER to record, ENTER again to stop, Ctrl-C to quit
python -m picos_ce --from en          # speak English, hear Spanish
python -m picos_ce --from es          # speak Spanish, hear English

# Type instead (no microphone needed)
python -m picos_ce --from en --text "search warrant"
```

Useful flags:

| Flag | What it does |
|------|--------------|
| `--model base` | Smaller, faster speech model for low-RAM machines (`tiny` is smaller still) |
| `--no-tts` | Don't speak the result out loud |
| `--glossary path/to/your.csv` | Use your own glossary |

The first recording takes a few extra seconds while the speech model loads, and it's normal for it to hear nothing on that first try.

**Translation precision.** PICOS runs Argos Translate at `compute_type=float32` (full precision) by default. A faster, lower-RAM `int8` mode exists, but on at least one CPU it made translation degenerate into repeated garbage instead of just being less accurate — so float32 is the default, not a suggestion. float32 costs roughly 4x an int8 model's memory; for these small (tens-of-MB) models that's a few hundred MB either way. Override with `PICOS_CE_COMPUTE_TYPE=auto` (or `int8`) only after confirming it's clean on your own hardware.

---

## The glossary

`data/glossary_en_es_starter.csv` has 30 common courtroom terms and is public domain. Open it in any spreadsheet app or text editor to add, edit, or replace terms — or point `--glossary` at a CSV of your own.

---

## How it works

Seven small files under `picos_ce/`, meant to be read top to bottom:

| File | What it does |
|------|--------------|
| `asr.py` | Records from the mic, transcribes with faster-whisper |
| `translate.py` | Runs Argos Translate |
| `guards.py` | Catches degenerate translation output before it reaches you |
| `glossary.py` | Swaps in the right legal term |
| `tts.py` | Speaks the result (Piper, or espeak-ng) |
| `pipeline.py` | Wires the stages together |
| `__main__.py` | The command line |

---

## Text-to-speech is optional

PICOS ships no speech engine and no voices. Without one it prints results instead of speaking them.

To hear it talk, either install `espeak-ng` (`sudo apt install espeak-ng`, robotic but instant), or install [Piper](https://github.com/OHF-Voice/piper1-gpl) and pick a voice:

```bash
pip install piper-tts
./scripts/setup_models.sh --voice en=VOICE_ID --voice es=VOICE_ID
```

Browse voices at [rhasspy/piper-voices](https://github.com/rhasspy/piper-voices/blob/main/VOICES.md). Each voice has its own license in its MODEL_CARD — the setup script shows it to you before downloading, but reading it is on you.

---

## Licensing

PICOS downloads nothing without showing you what it is and asking first. Every accepted download gets logged to `~/.local/share/picos-community/licenses-accepted.txt`.

| Flag | What it does |
|------|--------------|
| `--yes` | Accept every prompt (for scripts) |
| `--whisper` | Fetch the speech model now instead of on first use |
| `--voice LANG=ID` | Add a Piper voice (shows its MODEL_CARD first) |

---

## Disclaimer

PICOS Community Edition is a research and educational tool. It is provided **"as is," without warranty of any kind**, express or implied, as further detailed in the [GPLv3 license](LICENSE).

Automatic transcription and machine translation are inherently imperfect and **may produce inaccurate, incomplete, or misleading output**. This software is **not a substitute for a qualified human interpreter or translator**, and it does not provide legal advice. Do not rely on its output for legal proceedings, official filings, or any situation where accuracy matters without independent verification by a qualified professional. The author and contributors accept **no responsibility or liability** for errors in the output or for any consequences of its use.

---

## License

Code is [GPL v3](LICENSE). The starter glossary is public domain (CC0). Dependency licenses are in [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

---

## The full products

**PICOS Pocket** — reference terminology lookup for iPhone and iPad. Speak or type a term, get the equivalent large and spoken aloud. Free on the [App Store](https://apps.apple.com/us/app/picos-pocket/id6796009611).

**PICOS for Mac** — live streaming interpretation, domain-aware terminology, and session tools.

→ **[interpretforme.com](https://interpretforme.com)**

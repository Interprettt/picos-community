#!/usr/bin/env bash
# PICOS Community Edition — one-time model/voice setup (Linux).
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# STRICT DOWNLOAD LICENSING: nothing is downloaded until its license (or the
# best available license reference) has been SHOWN and you have confirmed. This
# script installs NO TTS engine and NO voices unless you explicitly ask for
# them. Every confirmed download is recorded in:
#     $DATA_DIR/licenses-accepted.txt
#
# Usage:
#   ./scripts/setup_models.sh [FROM:TO] [options]
#
#   (no args)                 show + confirm + install the Argos EN<->ES packages
#                             only, then print how to add TTS yourself.
#   FROM:TO                   language pair (default: en:es), e.g.  es:en
#   --yes                     accept every prompt (for scripted/unattended runs)
#   --whisper                 also fetch the faster-whisper ASR model now
#   --whisper-model NAME      which Whisper size to fetch (default: small)
#   --voice LANG=VOICE_ID     opt in to a Piper voice (repeatable), e.g.
#                             --voice es=es_MX-ald-medium --voice en=en_US-lessac-medium
#   -h, --help                show this help and exit
#
# You can also request a Piper voice via the environment:
#     PICOS_PIPER_VOICE_ES=es_MX-ald-medium ./scripts/setup_models.sh
#
# The pair is a parameter so new language pairs need no code changes.
set -euo pipefail

# --------------------------------------------------------------------------- #
# Defaults + argument parsing
# --------------------------------------------------------------------------- #
PAIR="en:es"
ASSUME_YES=0
DO_WHISPER=0
WHISPER_MODEL="small"
declare -a VOICE_REQUESTS=()

usage() { sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --yes|-y)        ASSUME_YES=1 ;;
        --whisper)       DO_WHISPER=1 ;;
        --whisper-model) shift; WHISPER_MODEL="${1:?--whisper-model needs a value}" ;;
        --whisper-model=*) WHISPER_MODEL="${1#*=}" ;;
        --voice)         shift; VOICE_REQUESTS+=("${1:?--voice needs LANG=VOICE_ID}") ;;
        --voice=*)       VOICE_REQUESTS+=("${1#*=}") ;;
        -h|--help)       usage; exit 0 ;;
        *:*)             PAIR="$1" ;;
        *) echo "ERROR: unknown argument '$1' (see --help)" >&2; exit 2 ;;
    esac
    shift
done

FROM="${PAIR%%:*}"
TO="${PAIR##*:}"
if [ -z "$FROM" ] || [ -z "$TO" ] || [ "$FROM" = "$TO" ]; then
    echo "ERROR: pair must be FROM:TO with two different languages (e.g. en:es)" >&2
    exit 2
fi

DATA_DIR="${PICOS_CE_HOME:-$HOME/.local/share/picos-community}"
VOICES_DIR="$DATA_DIR/piper/models"
LICENSE_LOG="$DATA_DIR/licenses-accepted.txt"
PIPER_VOICES_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Pull in any PICOS_PIPER_VOICE_<LANG> requests from the environment.
for L in "$FROM" "$TO"; do
    UP="$(printf '%s' "$L" | tr '[:lower:]' '[:upper:]')"
    eval "ENV_VOICE=\${PICOS_PIPER_VOICE_${UP}:-}"
    if [ -n "${ENV_VOICE:-}" ]; then
        if [ -f "$ENV_VOICE" ]; then
            echo "==> PICOS_PIPER_VOICE_${UP} points at an existing file — using it as-is:"
            echo "    $ENV_VOICE   (no download needed)"
        else
            VOICE_REQUESTS+=("${L}=${ENV_VOICE}")
        fi
    fi
done

echo "==> PICOS Community Edition setup — pair ${FROM}<->${TO}"
echo "    data dir:      $DATA_DIR"
echo "    license record: $LICENSE_LOG"
[ "$ASSUME_YES" = 1 ] && echo "    (--yes: all prompts auto-accepted)"
echo

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
confirm() {
    # $1 = prompt. Returns 0 (yes) / 1 (no). --yes auto-accepts. EOF => No.
    if [ "$ASSUME_YES" = 1 ]; then
        echo "    ${1} [--yes] accepted."
        return 0
    fi
    local ans=""
    if ! read -r -p "    ${1} [y/N] " ans; then
        echo; return 1   # EOF / no tty answer -> treat as No (install nothing)
    fi
    case "$ans" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

log_accept() {
    # $1=name  $2=source-url  $3=license-shown
    mkdir -p "$DATA_DIR"
    printf '%s\t%s\t%s\t%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1" "$2" "$3" >> "$LICENSE_LOG"
    echo "    logged to $(basename "$LICENSE_LOG"): $1"
}

# --------------------------------------------------------------------------- #
# 1) Argos Translate packages (both directions) — license-gated
# --------------------------------------------------------------------------- #
ARGOS_INDEX="https://www.argosopentech.com/argospm/index/"
ARGOS_LICENSE="CC-BY 4.0 (OPUS-MT derived model; the .argosmodel metadata does not embed a license field — see the Argos OpenTech package index / project licensing)"

echo "-------------------------------------------------------------------------"
echo "Argos Translate language packages (offline machine translation)"
echo "-------------------------------------------------------------------------"
echo "  Would install (both directions):"
echo "    * ${FROM} -> ${TO}"
echo "    * ${TO} -> ${FROM}"
echo "  Source:  Argos package index — ${ARGOS_INDEX}"
echo "  License: ${ARGOS_LICENSE}"
echo

if confirm "Download and install these Argos packages?"; then
    PICOS_FROM="$FROM" PICOS_TO="$TO" python3 - <<'PY'
import os, sys, re
import argostranslate.package as pkg

frm, to = os.environ["PICOS_FROM"], os.environ["PICOS_TO"]
pkg.update_package_index()
avail = pkg.get_available_packages()
installed = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
for a, b in [(frm, to), (to, frm)]:
    if (a, b) in installed:
        print(f"    {a}->{b} already installed"); continue
    match = next((p for p in avail if p.from_code == a and p.to_code == b), None)
    if not match:
        sys.exit(f"    ERROR: no Argos package for {a}->{b}")
    print(f"    downloading {a}->{b} ...", flush=True)
    pkg.install_from_path(match.download())
    print(f"    installed {a}->{b}", flush=True)

# Report the license each installed package actually states (visible only after
# install), so the accepted-licenses log records the real line.
for a, b in [(frm, to), (to, frm)]:
    ip = next((p for p in pkg.get_installed_packages()
               if p.from_code == a and p.to_code == b), None)
    lic = "not stated in README — see Argos OpenTech (OPUS-MT models are CC-BY 4.0)"
    if ip is not None:
        readme = ip.get_readme() or ""
        for line in readme.splitlines():
            if re.search(r'(?i)\b(cc-?by|cc0|licensed\s+(under\s+)?(cc|mit|apache|gpl))', line):
                lic = line.strip()
                break
    print(f"    {a}->{b} package README license: {lic}")

# Normalize each package's bundled Stanza tokenizer (sentence-boundary
# detection) ONE time, now, while we're already in a sanctioned network
# window -- not silently at first translate. Every Argos package that
# doesn't ship a MiniSBD model instead bundles a Stanza resources.json
# snapshot from whenever it was built; that snapshot can predate fields the
# installed `stanza` package's client code expects (e.g. a "packages" key),
# which crashes sentence splitting outright. Constructing the pipeline once
# here lets Stanza self-heal the manifest via ITS default (network) method
# while a real fetch is still allowed; picos_ce/translate.py then freezes
# it -- no further Stanza network access after this script exits. See
# translate.py's _force_stanza_offline() docstring for the full story.
try:
    import stanza
except ImportError:
    stanza = None
if stanza is not None:
    installed_now = pkg.get_installed_packages()
    for lang in {frm, to}:
        ip = next((p for p in installed_now if p.from_code == lang), None)
        if ip is None:
            continue
        stanza_dir = ip.package_path / "stanza"
        minisbd_dir = ip.package_path / "minisbd"
        if not stanza_dir.exists() or minisbd_dir.exists():
            continue  # this package doesn't use Stanza for SBD -- nothing to normalize
        print(f"    normalizing Stanza tokenizer resources for '{lang}' "
              f"(stanfordnlp/stanza-resources, Apache-2.0) ...", flush=True)
        try:
            stanza.Pipeline(lang=lang, dir=str(stanza_dir), processors="tokenize",
                             download_method=stanza.DownloadMethod.DOWNLOAD_RESOURCES,
                             logging_level="WARNING")
            print(f"    '{lang}' tokenizer resources ready (frozen after this).", flush=True)
        except Exception as e:
            print(f"    WARNING: could not normalize Stanza resources for '{lang}': {e}",
                  file=sys.stderr)
            print(f"             translation may still work using the package's own "
                  f"bundled files; see README if '{lang}' sentences fail to split.",
                  file=sys.stderr)
PY
    log_accept "Argos ${FROM}<->${TO} packages" "$ARGOS_INDEX" "$ARGOS_LICENSE"
    echo "    Argos packages ready."
else
    echo "    Skipped Argos packages — nothing installed."
    echo "    (PICOS needs these to translate; re-run and accept when ready.)"
fi
echo

# --------------------------------------------------------------------------- #
# 2) Whisper ASR model (only with --whisper) — license-gated
# --------------------------------------------------------------------------- #
if [ "$DO_WHISPER" = 1 ]; then
    WHISPER_REPO="Systran/faster-whisper-${WHISPER_MODEL}"
    WHISPER_URL="https://huggingface.co/${WHISPER_REPO}"
    WHISPER_LICENSE="MIT (OpenAI Whisper weights, CTranslate2-converted by SYSTRAN)"
    echo "-------------------------------------------------------------------------"
    echo "Whisper speech-recognition model (faster-whisper)"
    echo "-------------------------------------------------------------------------"
    echo "  Model:   ${WHISPER_REPO}"
    echo "  Source:  Hugging Face — ${WHISPER_URL}"
    echo "  License: ${WHISPER_LICENSE}"
    echo "           (verify the exact terms on the model page above.)"
    echo
    if confirm "Download the '${WHISPER_MODEL}' Whisper model now?"; then
        WHISPER_MODEL="$WHISPER_MODEL" python3 - <<'PY'
import os
from faster_whisper import WhisperModel
size = os.environ["WHISPER_MODEL"]
print(f"    fetching {size} (this can take a while)...", flush=True)
WhisperModel(size, device="cpu", compute_type="int8")  # triggers the HF download
print("    Whisper model cached.", flush=True)
PY
        log_accept "Whisper ${WHISPER_REPO}" "$WHISPER_URL" "$WHISPER_LICENSE"
    else
        echo "    Skipped — faster-whisper will fetch it (with this same notice) on first mic run."
    fi
    echo
else
    echo "Whisper ASR model: not fetched now (pass --whisper to fetch it here)."
    echo "  faster-whisper downloads it automatically on your first mic run:"
    echo "    model  Systran/faster-whisper-${WHISPER_MODEL}  (Hugging Face, MIT)."
    echo
fi

# --------------------------------------------------------------------------- #
# 3) Piper voices (fully opt-in) — MODEL_CARD shown before every download
# --------------------------------------------------------------------------- #
# Parse a Piper VOICE_ID (e.g. es_MX-ald-medium) into its repo sub-path.
# Sets VOICE_DIR + VOICE_FILE, or returns nonzero for a malformed id.
parse_voice_id() {
    local id="$1"
    local IFS='-'
    local -a parts=($id)
    [ "${#parts[@]}" -ge 3 ] || return 1
    local region="${parts[0]}"                       # es_MX
    local quality="${parts[$((${#parts[@]}-1))]}"    # medium
    local family="${region%%_*}"                     # es
    [ "$family" != "$region" ] && [ -n "$family" ] || return 1   # region must be lang_REGION
    case "$quality" in x_low|low|medium|high) ;; *) return 1 ;; esac
    local name="" i
    for ((i=1; i<${#parts[@]}-1; i++)); do name+="${parts[$i]}-"; done
    name="${name%-}"
    [ -n "$name" ] || return 1
    VOICE_DIR="$family/$region/$name/$quality"
    VOICE_FILE="$id.onnx"
}

install_voice() {
    local lang="$1" id="$2"
    echo "-------------------------------------------------------------------------"
    echo "Piper voice request:  ${lang} = ${id}"
    echo "-------------------------------------------------------------------------"
    if ! parse_voice_id "$id"; then
        echo "  ERROR: '${id}' is not a valid Piper voice id." >&2
        echo "         Expected  <locale>-<name>-<quality>, e.g. es_MX-ald-medium." >&2
        echo "         Browse valid ids at https://github.com/rhasspy/piper-voices/blob/main/VOICES.md" >&2
        return 3
    fi

    mkdir -p "$VOICES_DIR"
    local card_url="$PIPER_VOICES_BASE/$VOICE_DIR/MODEL_CARD"
    local card_dest="$VOICES_DIR/${id}.MODEL_CARD"
    echo "  Fetching MODEL_CARD (license/lineage) FIRST:"
    echo "    $card_url"
    if curl -fsSL "$card_url" -o "$card_dest"; then
        echo "  ---- MODEL_CARD (key lines) --------------------------------------"
        grep -iE 'dataset|license|finetuned from|training' "$card_dest" | sed 's/^/    /' || \
            echo "    (no dataset/license/lineage lines matched — read $card_dest in full)"
        echo "  ------------------------------------------------------------------"
        echo "  NOTE: 'Finetuned from ...' lineage may chain further than this one card."
        echo "        You are responsible for reviewing the full dataset license chain."
    else
        rm -f "$card_dest"
        echo "  WARNING: could not fetch the MODEL_CARD for '${id}'." >&2
        echo "           Its license/lineage could NOT be shown. Proceed only if you" >&2
        echo "           have reviewed it yourself at rhasspy/piper-voices." >&2
    fi
    echo

    if ! confirm "Download voice '${id}' (.onnx + config)?"; then
        echo "    Skipped voice '${id}' — nothing downloaded."
        rm -f "$card_dest"
        return 0
    fi

    local onnx_url="$PIPER_VOICES_BASE/$VOICE_DIR/$VOICE_FILE"
    local onnx_dest="$VOICES_DIR/$VOICE_FILE"
    echo "    downloading $VOICE_FILE ..."
    if ! curl -fsSL "$onnx_url"       -o "$onnx_dest" \
        || ! curl -fsSL "$onnx_url.json" -o "$onnx_dest.json"; then
        echo "  ERROR: download failed for '${id}' (does the voice exist?)." >&2
        rm -f "$onnx_dest" "$onnx_dest.json"
        return 3
    fi
    log_accept "Piper voice ${id}" "$onnx_url" "see ${id}.MODEL_CARD (dataset-specific)"
    echo "    voice '${id}' ready (MODEL_CARD saved as ${id}.MODEL_CARD)."
}

if [ "${#VOICE_REQUESTS[@]}" -gt 0 ]; then
    for req in "${VOICE_REQUESTS[@]}"; do
        vlang="${req%%=*}"
        vid="${req#*=}"
        if [ -z "$vlang" ] || [ -z "$vid" ] || [ "$vlang" = "$req" ]; then
            echo "ERROR: --voice needs LANG=VOICE_ID (got '${req}')" >&2
            exit 2
        fi
        install_voice "$vlang" "$vid"   # nonzero (set -e) aborts on a bad/failed voice
        echo
    done
fi

# --------------------------------------------------------------------------- #
# 4) TTS guidance (always) — PICOS CE ships no engine and no voices
# --------------------------------------------------------------------------- #
echo "-------------------------------------------------------------------------"
echo "Text-to-speech (optional — PICOS CE ships NO TTS engine and NO voices)"
echo "-------------------------------------------------------------------------"
echo "  PICOS speaks only if you provide a voice yourself. Options:"
echo
echo "  1) Piper (natural, neural) — install the engine yourself:"
echo "       pip install piper-tts"
echo "       # or grab a release from https://github.com/OHF-Voice/piper1-gpl"
echo "     Then add a voice with this script, e.g.:"
echo "       ./scripts/setup_models.sh --voice ${TO}=es_MX-ald-medium --voice ${FROM}=en_US-lessac-medium"
echo "     Browse voices:  https://github.com/rhasspy/piper-voices/blob/main/VOICES.md"
echo "     Each voice's MODEL_CARD carries its OWN dataset license — this script"
echo "     shows it before every download, but reviewing it is your responsibility."
echo
echo "  2) espeak-ng (robotic, zero-config fallback):"
echo "       sudo apt install espeak-ng"
echo
if command -v piper >/dev/null 2>&1; then
    echo "  Detected: piper engine on PATH."
elif command -v espeak-ng >/dev/null 2>&1; then
    echo "  Detected: espeak-ng (fallback) on PATH — PICOS will use it if no Piper voice is set."
else
    echo "  Detected: no TTS engine yet — PICOS will run with speech disabled until you add one."
fi
echo
echo "==> Done. Try:  python -m picos_ce --from ${FROM} --text \"restraining order\""

# PICOS Community Edition — machine translation (Argos Translate)
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
Offline machine translation via Argos Translate.

The language pair is a parameter, not a hardcode: every function takes ISO
language codes (from_lang, to_lang). Version 0.1 ships and documents English
<-> Spanish only (DEFAULT_FROM / DEFAULT_TO), but adding another pair later is
just a matter of installing its Argos packages and voices — no code change.

Argos is used through its public API with no modifications. Language packages
are installed by scripts/setup_models.sh. This module just translates text one
way; it keeps no glossary or per-context state of its own.

Two exceptions, both below: Argos itself is untouched in each case, but its
dependencies get a targeted runtime patch. _force_stanza_offline() stops the
transitive Stanza dependency (sentence-boundary detection) from quietly
re-fetching its resource manifest over the network on every call -- a real,
separate offline-guarantee gap, unrelated to the paragraph below.
_force_float32_compute_type() fixes a field-confirmed root cause: Argos asks
CTranslate2 for compute_type="auto", which resolves to int8 on some CPUs
(confirmed: an AMD x86 box), and the es->en model degenerates under int8 on
that hardware -- same package, same tokens, float32 correct, int8 garbage,
on the same machine. Two earlier rounds chasing this same field report (a
suspected Stanza/manifest interaction, then a suspected missing CTranslate2
repetition guard) were both tested directly and ruled out; see this file's
git history if you want the full trail. See each function's docstring below
for the current story.
"""
from __future__ import annotations

import os

# v0.1 default pair (English <-> Spanish). Changing these does not require
# touching any other module.
DEFAULT_FROM = "en"
DEFAULT_TO = "es"

_stanza_patched = False  # module-level guard so the patch below applies once


def _force_stanza_offline() -> None:
    """
    Stop stanza -- a TRANSITIVE dependency pulled in by argostranslate for
    sentence-boundary detection, never imported by picos_ce directly -- from
    phoning home on every translation.

    argostranslate's StanzaSentencizer (argostranslate/sbd.py) constructs
    ``stanza.Pipeline(lang=..., dir=<package>/stanza, processors="tokenize",
    ...)`` with no ``download_method``, so stanza defaults to
    ``DownloadMethod.DOWNLOAD_RESOURCES``: on EVERY call it fetches the
    CURRENT resources.json from stanfordnlp/stanza-resources on GitHub and
    overwrites the manifest sitting in the installed .argosmodel package --
    not just once at setup, but on every single translate() call. That is
    both an offline-guarantee gap PICOS's own audit missed (stanza is
    transitive, not a direct import) and a stability risk: whatever that
    manifest says *right now* silently changes what stanza loads, with no
    version pin.

    You would think the fix is simply "never let it re-fetch" -- but the
    .argosmodel's OWN bundled resources.json snapshot can itself be too old
    for the installed `stanza` client: on the reference machine, the
    "en_es" package ships a manifest missing a "packages" key that
    stanza 1.10.1's add_mwt() requires unconditionally, so EN->ES sentence
    splitting hard-crashes with a raw KeyError the moment the network fetch
    that would otherwise have silently repaired it is blocked. So this can't
    be "freeze on first sight of a bundled file" -- it has to be "freeze
    only once a compatible manifest is confirmed on disk."

    ``scripts/setup_models.sh`` now does that confirmation itself: right
    after a license-confirmed Argos package install, it constructs a real
    ``stanza.Pipeline(..., download_method=DOWNLOAD_RESOURCES)`` once per
    installed language, in the same sanctioned network window, so any
    manifest/model mismatch is repaired there -- not silently at runtime.
    This function's job is just to make sure NOTHING re-touches the network
    after that: it patches stanza's resources-refresh entry point to reuse
    whatever resources.json is already on disk (stanza's own
    ``DownloadMethod.REUSE_RESOURCES`` behavior; argostranslate's hardcoded
    call gives us no way to request that directly) and raises a clear,
    actionable picos_ce error -- pointing at setup_models.sh -- instead of
    a raw stanza traceback if it's missing.

    Idempotent and safe to call before every translate(): patches once
    (module-level guard) and does nothing if stanza isn't installed.
    """
    global _stanza_patched
    if _stanza_patched:
        return
    try:
        import stanza.pipeline.core as _stanza_core
        import stanza.resources.common as _stanza_common
    except ImportError:
        _stanza_patched = True  # nothing to patch; argostranslate will fall
        return                  # back to MiniSBD/spaCy without stanza at all

    def _frozen_resources_json(model_dir=None, *args, **kwargs):
        if model_dir and os.path.exists(os.path.join(model_dir, "resources.json")):
            return  # reuse the manifest already on disk -- no network call
        raise RuntimeError(
            f"Stanza tokenizer resources are missing at {model_dir!r} and "
            f"PICOS does not fetch them at translate-time (offline "
            f"guarantee). Run:  ./scripts/setup_models.sh  to install/repair "
            f"them, then try again."
        )

    # download_resources_json is imported by name into stanza.pipeline.core
    # (`from stanza.resources.common import ..., download_resources_json,
    # ...`), so both bindings must be patched -- core.py calls its own local
    # copy of the name, not an attribute lookup through the common module.
    _stanza_common.download_resources_json = _frozen_resources_json
    _stanza_core.download_resources_json = _frozen_resources_json
    _stanza_patched = True


_compute_type_forced = False  # module-level guard so this patch applies once

# Advanced-use escape hatch: set this to override PICOS's float32 default
# (e.g. "auto" or "int8" for lower RAM / higher speed) once you've verified
# it doesn't degenerate on YOUR hardware -- see the README's note on this.
COMPUTE_TYPE_ENV_VAR = "PICOS_CE_COMPUTE_TYPE"
DEFAULT_COMPUTE_TYPE = "float32"


def _force_float32_compute_type() -> None:
    """
    Force CTranslate2's compute_type to float32 for Argos translation.

    ROOT CAUSE (confirmed on real hardware, not speculation) of a field
    report of ES->EN degenerating into repeated garbage
    ("mainstremainstremainstre...@@") on some machines, EN->ES unaffected:
    argostranslate.settings.compute_type defaults to "auto"
    (ARGOS_COMPUTE_TYPE env var, default "auto"), which CTranslate2 resolves
    per-CPU to the fastest supported type. On an affected AMD x86 machine
    that resolves to int8, and the es->en model degenerates under int8 --
    same package, same tokens, same machine: float32 and the library
    default both translate correctly, int8 alone produces the garbage. Two
    earlier rounds chasing this same report (Stanza/manifest interaction,
    then a suspected missing CTranslate2 repetition guard) were each tested
    directly and ruled out before this was found; this is the confirmed fix.

    argostranslate reads settings.compute_type fresh each time it lazily
    constructs its ctranslate2.Translator (PackageTranslation.hypotheses()),
    and settings.compute_type is a plain module attribute, not a function
    hidden behind an API -- so unlike the other two patches in this file,
    this needs no wrapping, just setting it before the first translate().

    float32 uses roughly 4x an int8 model's memory and is slower per token;
    for these small Argos models (tens of MB) that's not a lot in absolute
    terms, but see the README for the tradeoff. Override with the
    PICOS_CE_COMPUTE_TYPE env var (e.g. "auto" or "int8") only after you've
    confirmed your own hardware doesn't hit this.

    Idempotent and safe to call before every translate(): sets once
    (module-level guard) and does nothing if argostranslate isn't installed.
    """
    global _compute_type_forced
    if _compute_type_forced:
        return
    try:
        from argostranslate import settings as _argos_settings
    except ImportError:
        _compute_type_forced = True
        return
    _argos_settings.compute_type = os.environ.get(COMPUTE_TYPE_ENV_VAR, DEFAULT_COMPUTE_TYPE)
    _compute_type_forced = True


def _argos_translate():
    try:
        from argostranslate import translate
    except ImportError as e:  # pragma: no cover - environment guard
        raise RuntimeError(
            "argostranslate is not installed. Run: pip install -r requirements.txt"
        ) from e
    _force_stanza_offline()
    _force_float32_compute_type()
    return translate


def _argos_package():
    try:
        from argostranslate import package
    except ImportError as e:  # pragma: no cover - environment guard
        raise RuntimeError(
            "argostranslate is not installed. Run: pip install -r requirements.txt"
        ) from e
    return package


def installed_pairs() -> set[tuple[str, str]]:
    """Return the (from_code, to_code) language pairs Argos has installed.

    Read directly from the installed *packages*. Older releases exposed the
    pairs via ``Language.translations`` on ``translate.get_installed_languages()``,
    but that attribute was renamed/removed upstream (field-proven on Argos
    1.11.0), so we go through ``package.get_installed_packages()`` instead.
    """
    package = _argos_package()
    return {(p.from_code, p.to_code) for p in package.get_installed_packages()}


def ensure_available(from_lang: str, to_lang: str) -> None:
    """Raise a clear error if the needed Argos package isn't installed."""
    if from_lang == to_lang:
        raise ValueError("from_lang and to_lang must differ")
    if (from_lang, to_lang) not in installed_pairs():
        raise RuntimeError(
            f"Argos {from_lang}->{to_lang} language package is not installed.\n"
            f"Install it with:  ./scripts/setup_models.sh {from_lang}:{to_lang}\n"
            f"(v0.1 ships EN<->ES; see README.)"
        )


def translate(text: str, from_lang: str, to_lang: str) -> str:
    """Translate `text` from `from_lang` to `to_lang` (ISO codes, e.g. en/es)."""
    text = (text or "").strip()
    if not text:
        return ""
    argos = _argos_translate()
    return argos.translate(text, from_lang, to_lang)

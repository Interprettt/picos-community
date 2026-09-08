# PICOS Community Edition — test suite
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Small, fast, offline tests. They do NOT download models or hit the network:
# the Argos MT call is monkeypatched, and the setup-script tests only exercise
# argument validation / the "declined" path (no install).
#
# Run:  pip install pytest   &&   pytest -q
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = REPO_ROOT / "data" / "glossary_en_es_starter.csv"
SETUP_SH = REPO_ROOT / "scripts" / "setup_models.sh"

sys.path.insert(0, str(REPO_ROOT))

from picos_ce import asr                      # noqa: E402
from picos_ce import translate as mt          # noqa: E402
from picos_ce.glossary import Glossary, normalize  # noqa: E402
from picos_ce.guards import (  # noqa: E402
    TRANSLATION_FAILED,
    is_suspicious_translation,
    looks_degenerate,
    normalize_asr,
)
from picos_ce.pipeline import Pipeline        # noqa: E402


# --------------------------------------------------------------------------- #
# 7a. installed_pairs() reads pairs from get_installed_packages() (API drift)
# --------------------------------------------------------------------------- #
class _FakePkg:
    def __init__(self, frm, to):
        self.from_code = frm
        self.to_code = to


class _FakePackageModule:
    def get_installed_packages(self):
        return [_FakePkg("en", "es"), _FakePkg("es", "en"), _FakePkg("en", "fr")]


def test_installed_pairs_uses_packages(monkeypatch):
    # The pinned argostranslate (1.11.0) dropped Language.translations; the fix
    # must read (from_code, to_code) off get_installed_packages().
    monkeypatch.setattr(mt, "_argos_package", lambda: _FakePackageModule())
    pairs = mt.installed_pairs()
    assert pairs == {("en", "es"), ("es", "en"), ("en", "fr")}


def test_ensure_available_uses_installed_pairs(monkeypatch):
    monkeypatch.setattr(mt, "_argos_package", lambda: _FakePackageModule())
    mt.ensure_available("es", "en")            # present -> no raise
    with pytest.raises(RuntimeError):
        mt.ensure_available("es", "de")        # absent -> clear error


# --------------------------------------------------------------------------- #
# 7b. A glossary hit short-circuits MT in BOTH directions
# --------------------------------------------------------------------------- #
def _boom(*_a, **_k):
    raise AssertionError("MT must not be called on a glossary hit")


def test_glossary_shortcircuits_es_to_en(monkeypatch):
    monkeypatch.setattr(mt, "translate", _boom)
    pipe = Pipeline("es", "en", glossary_path=str(GLOSSARY), speak_result=False)
    assert pipe.translate_text("acusado") == "defendant"


def test_glossary_shortcircuits_en_to_es(monkeypatch):
    monkeypatch.setattr(mt, "translate", _boom)
    pipe = Pipeline("en", "es", glossary_path=str(GLOSSARY), speak_result=False)
    assert pipe.translate_text("restraining order") == "orden de restricción"


def test_glossary_lookup_both_directions():
    g = Glossary(str(GLOSSARY))
    assert g.lookup("acusado", "es") == "defendant"
    assert g.lookup("defendant", "en") == "acusado"
    assert g.lookup("not a legal term at all", "es") is None


def test_glossary_no_substring_corruption():
    # Regression: "demandado" must NOT be mangled by the "demanda" entry.
    g = Glossary(str(GLOSSARY))
    assert "complaint" not in g.apply("demandado", "es")
    assert g.apply("demandado", "es") == "demandado"


# --------------------------------------------------------------------------- #
# 7c. Repetition / length guard triggers on degenerate output, passes normal
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", [
    "mainstre" * 40,                 # chunk repeated many times (the live bug)
    "aaaaaaaaaaaa",                  # single-char run
    "the the the the the the the",   # repeated word
])
def test_looks_degenerate_flags_bad(bad):
    assert looks_degenerate(bad) is True


@pytest.mark.parametrize("ok", [
    "defendant",
    "orden de restricción",
    "The defendant paid his bail.",
    "of command",
])
def test_looks_degenerate_passes_normal(ok):
    assert looks_degenerate(ok) is False


def test_is_suspicious_translation():
    assert is_suspicious_translation("demandado", "mainstre" * 50) is True   # degenerate
    assert is_suspicious_translation("a", "x" * 60) is True                  # length blow-up
    assert is_suspicious_translation("demandado", "defendant") is False      # fine
    assert is_suspicious_translation("bail", "fianza") is False              # fine


def test_pipeline_rejects_degenerate_mt(monkeypatch):
    monkeypatch.setattr(mt, "translate", lambda *_a, **_k: "mainstre" * 60)
    pipe = Pipeline("es", "en", glossary_path=str(GLOSSARY), speak_result=False)
    # "audiencia" is not a glossary term, so it reaches (the faked) MT and is
    # rejected. (Was "fianza" -- the 30-term starter glossary now includes
    # bail/fianza, so that word short-circuits before ever reaching MT.)
    assert pipe.translate_text("audiencia") == TRANSLATION_FAILED


def test_pipeline_passes_good_mt(monkeypatch):
    monkeypatch.setattr(mt, "translate", lambda *_a, **_k: "hearing")
    pipe = Pipeline("es", "en", glossary_path=str(GLOSSARY), speak_result=False)
    assert pipe.translate_text("audiencia") == "hearing"


# --------------------------------------------------------------------------- #
# 7d. The normalizer turns "De mandado." into a glossary-matchable form
# --------------------------------------------------------------------------- #
def test_normalize_asr_makes_matchable():
    out = normalize_asr("De mandado.")
    assert out == "de mandado"                 # case-folded, terminal punct stripped
    assert out == out.lower()
    assert not out.endswith(".")
    # "matchable" == it lives in the same normalized space the glossary matches in
    assert normalize(out) == normalize("De mandado.")


@pytest.mark.parametrize("raw,expected", [
    ("  Restraining Order!  ", "restraining order"),
    ("¿Fianza?", "fianza"),
    ("THE DEFENDANT", "the defendant"),
    ("", ""),
])
def test_normalize_asr_examples(raw, expected):
    assert normalize_asr(raw) == expected


# --------------------------------------------------------------------------- #
# 7e. Setup script: bogus --voice fails loudly; no-flag decline installs nothing
# --------------------------------------------------------------------------- #
def _run_setup(args, tmp_path):
    return subprocess.run(
        ["bash", str(SETUP_SH), *args],
        stdin=subprocess.DEVNULL,              # EOF -> every prompt declines
        capture_output=True, text=True,
        env={"PICOS_CE_HOME": str(tmp_path), "PATH": _os_path()},
    )


def _os_path():
    import os
    return os.environ.get("PATH", "/usr/bin:/bin")


# --------------------------------------------------------------------------- #
# Offline guarantee: ASR loads offline when cached, and fails friendly when not
# --------------------------------------------------------------------------- #
class _FakeWhisper:
    instances = []

    def __init__(self, size, **kwargs):
        self.size = size
        self.kwargs = kwargs
        _FakeWhisper.instances.append(self)


def test_load_model_offline_when_cached(monkeypatch):
    # model present + HF_HUB_OFFLINE=1 => constructs offline, never raises.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setattr(asr, "model_is_cached", lambda *a, **k: True)
    monkeypatch.setattr("faster_whisper.WhisperModel", _FakeWhisper)
    _FakeWhisper.instances.clear()

    model = asr.load_model("small")            # must not raise, must not download

    assert isinstance(model, _FakeWhisper)
    assert model.kwargs.get("local_files_only") is True   # offline construction
    assert os.environ["HF_HUB_OFFLINE"] == "1"            # process locked offline


def test_load_model_absent_tells_user_to_run_setup(monkeypatch):
    # model missing + no sanctioned download => friendly RuntimeError, not a
    # raw huggingface_hub traceback.
    monkeypatch.setattr(asr, "model_is_cached", lambda *a, **k: False)
    with pytest.raises(RuntimeError) as exc:
        asr.load_model("small")                # allow_download defaults to False
    msg = str(exc.value)
    assert "setup_models.sh" in msg and "--whisper" in msg


def test_model_is_cached_accepts_local_dir(tmp_path):
    # a real directory path is "local" without any network probe
    assert asr.model_is_cached(str(tmp_path)) is True


@pytest.mark.skipif(not SETUP_SH.exists(), reason="setup script missing")
def test_setup_bogus_voice_fails_loudly(tmp_path):
    r = _run_setup(["--voice", "es=bogus"], tmp_path)
    assert r.returncode != 0
    assert "not a valid" in (r.stdout + r.stderr).lower()


@pytest.mark.skipif(not SETUP_SH.exists(), reason="setup script missing")
def test_setup_no_flag_declined_installs_nothing(tmp_path):
    r = _run_setup([], tmp_path)
    assert r.returncode == 0
    assert "nothing installed" in (r.stdout + r.stderr).lower()
    # nothing was downloaded => no accepted-licenses log was written
    assert not (tmp_path / "licenses-accepted.txt").exists()


# --------------------------------------------------------------------------- #
# 7f. Stanza offline hardening (transitive dependency, missed by the earlier
# audit — see translate.py's _force_stanza_offline() docstring for why the
# obvious "just freeze whatever's bundled" fix is unsafe on its own).
# --------------------------------------------------------------------------- #
def test_force_stanza_offline_reuses_existing_resources_without_network(tmp_path, monkeypatch):
    stanza_common = pytest.importorskip("stanza.resources.common")
    import stanza.pipeline.core as stanza_core

    mt._force_stanza_offline()  # idempotent — safe even if already patched

    resources_file = tmp_path / "resources.json"
    resources_file.write_text('{"already": "here"}')

    def _boom(*_a, **_k):
        raise AssertionError("stanza tried to hit the network for resources.json")
    monkeypatch.setattr(stanza_common.requests, "get", _boom)

    # download_resources_json is imported by NAME into stanza.pipeline.core
    # (a separate reference, not an attribute lookup through the common
    # module) — both bindings must behave, so both are exercised here.
    stanza_common.download_resources_json(str(tmp_path))
    stanza_core.download_resources_json(str(tmp_path))

    assert resources_file.read_text() == '{"already": "here"}'  # left untouched


def test_force_stanza_offline_raises_friendly_error_when_missing(tmp_path):
    stanza_common = pytest.importorskip("stanza.resources.common")
    mt._force_stanza_offline()

    with pytest.raises(RuntimeError) as exc:
        stanza_common.download_resources_json(str(tmp_path))  # no resources.json here
    msg = str(exc.value)
    assert "setup_models.sh" in msg
    assert "offline guarantee" in msg.lower()


def test_force_float32_compute_type_default(monkeypatch):
    # Confirmed root cause on real hardware (AMD x86): argostranslate's
    # compute_type="auto" resolves to int8 on that CPU, and the es->en model
    # degenerates under int8 -- same package, same tokens, float32 correct.
    # See _force_float32_compute_type()'s docstring for the full story
    # (including the two earlier theories this superseded).
    argos_settings = pytest.importorskip("argostranslate.settings")
    monkeypatch.delenv(mt.COMPUTE_TYPE_ENV_VAR, raising=False)
    monkeypatch.setattr(mt, "_compute_type_forced", False)

    argos_settings.compute_type = "auto"  # simulate argostranslate's own default
    mt._force_float32_compute_type()

    assert argos_settings.compute_type == "float32"


def test_force_float32_compute_type_respects_env_override(monkeypatch):
    argos_settings = pytest.importorskip("argostranslate.settings")
    monkeypatch.setenv(mt.COMPUTE_TYPE_ENV_VAR, "int8")
    monkeypatch.setattr(mt, "_compute_type_forced", False)

    mt._force_float32_compute_type()

    assert argos_settings.compute_type == "int8"


def test_force_float32_compute_type_is_idempotent(monkeypatch):
    argos_settings = pytest.importorskip("argostranslate.settings")
    monkeypatch.delenv(mt.COMPUTE_TYPE_ENV_VAR, raising=False)
    monkeypatch.setattr(mt, "_compute_type_forced", False)

    mt._force_float32_compute_type()
    assert argos_settings.compute_type == "float32"

    # A later env change must NOT retroactively apply -- the patch already
    # ran once (module-level guard), matching "set once before first
    # translate()", not "re-check on every call".
    monkeypatch.setenv(mt.COMPUTE_TYPE_ENV_VAR, "int8")
    mt._force_float32_compute_type()
    assert argos_settings.compute_type == "float32"


# --------------------------------------------------------------------------- #
# 7g. Real ES<->EN regression. Skipped unless the Argos packages are actually
# installed (e.g. after ./scripts/setup_models.sh), so the default fast/
# offline test run doesn't need them — but on a fully set-up machine (the
# only place the field-reported degeneration ever showed up) these exercise
# real MT, not a monkeypatched stand-in.
# --------------------------------------------------------------------------- #
def _es_en_installed() -> bool:
    try:
        return {("es", "en"), ("en", "es")} <= mt.installed_pairs()
    except Exception:
        return False


_ES_EN_REASON = "Argos es<->en packages not installed — run ./scripts/setup_models.sh"


@pytest.mark.skipif(not _es_en_installed(), reason=_ES_EN_REASON)
def test_real_es_to_en_single_word_not_degenerate():
    # Regression for the field-reported "mainstremainstre...@@" degeneration.
    # "demandado" is not itself a glossary term (see
    # test_glossary_no_substring_corruption), so this exercises real MT.
    out = mt.translate("demandado", "es", "en")
    assert out.strip() != ""
    assert not looks_degenerate(out)
    assert len(out) < 40  # not a length blow-up either


@pytest.mark.skipif(not _es_en_installed(), reason=_ES_EN_REASON)
def test_real_es_to_en_full_sentence_not_degenerate():
    out = mt.translate("el acusado tiene derecho a un abogado", "es", "en")
    assert not looks_degenerate(out)
    assert "attorney" in out.lower() or "lawyer" in out.lower()


@pytest.mark.skipif(not _es_en_installed(), reason=_ES_EN_REASON)
def test_real_translate_never_mutates_installed_stanza_resources():
    # The actual regression this audit round is about: translating must
    # never silently rewrite an installed package's stanza/resources.json.
    # That unconditional per-call refetch was the offline-guarantee gap; see
    # translate.py's _force_stanza_offline().
    import argostranslate.package as pkg

    resource_files = [
        p.package_path / "stanza" / "resources.json"
        for p in pkg.get_installed_packages()
        if (p.package_path / "stanza" / "resources.json").exists()
    ]
    assert resource_files, "expected at least one installed package with a stanza/resources.json"
    before = {f: f.read_bytes() for f in resource_files}

    mt.translate("demandado", "es", "en")
    mt.translate("restraining order", "en", "es")

    after = {f: f.read_bytes() for f in resource_files}
    assert before == after

# PICOS Community Edition — package root
# Copyright (C) 2026 David F. Proano Celi <interprettt@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of PICOS Community Edition, free software under the GNU
# General Public License v3 (or later). See the LICENSE file. NO WARRANTY.
"""
PICOS Community Edition — the open-source core of PICOS.

A bare-bones, fully offline speech-translation pipeline for one language pair
(English <-> Spanish):

    transcribe (faster-whisper) -> translate (Argos Translate) ->
    basic glossary substitution -> speak (Piper, espeak-ng fallback)

This is a deliberately minimal teaching edition — one language pair, a
command-line interface, and a small starter glossary. The full-featured product
is PICOS for Mac — https://interpretforme.com
"""

__version__ = "0.1.0"
__author__ = "David F. Proano Celi"

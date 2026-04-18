"""Profile routes package — /language-profiles/*, /glossary/*, /prompt-presets/*.

Submodules:
    language.py  — /language-profiles CRUD + assign + set-default
    glossary.py  — /glossary CRUD + TSV export
    presets.py   — /prompt-presets CRUD + default getter
"""

import logging

from flask import Blueprint

bp = Blueprint("profiles", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)

# Submodule imports run at the bottom so `bp` is already defined when the
# @bp.route decorators execute.
from routes.profiles import glossary, language, presets  # noqa: E402, F401

"""Test environment defaults.

Loaded before any test module imports, which matters: ``app.config``
builds its ``settings`` at import time and some fields are mandatory. The
defaults below let the suite run with no ``.env``; a configured value
always wins, because pydantic-settings ranks the environment above the
dotenv file, and seeding the environment unconditionally would override it.
"""

import os
from pathlib import Path

from dotenv import dotenv_values

_TEST_DEFAULTS = {
    # Obvious fakes: no offline test connects, and an accidental live call
    # should fail rather than land somewhere real.
    "db_uri": "postgresql+psycopg://test:test@localhost:5432/test",
    "secret_key": "test-secret-key-not-for-production-use",
    "bcrypt_rounds": "4",
}
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_CONFIGURED = dotenv_values(_ENV_FILE) if _ENV_FILE.exists() else {}

for _key, _value in _TEST_DEFAULTS.items():
    os.environ.setdefault(_key, _CONFIGURED.get(_key) or _value)

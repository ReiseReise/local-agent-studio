from __future__ import annotations

import pytest

from local_agent_studio.security import (
    DevelopmentSecretBox,
    SecretProtectionError,
    hash_password,
    verify_password,
)
from local_agent_studio.settings import Settings


def test_password_hash_and_secret_envelope_fail_closed():
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong password", encoded)

    box = DevelopmentSecretBox(b"one-long-development-secret")
    encrypted = box.protect("model-key")
    assert b"model-key" not in encrypted
    assert box.unprotect(encrypted) == "model-key"
    with pytest.raises(SecretProtectionError):
        DevelopmentSecretBox(b"another-long-development-secret").unprotect(encrypted)


def test_settings_reject_non_loopback(tmp_path):
    with pytest.raises(RuntimeError, match="loopback"):
        Settings(environment="test", host="0.0.0.0", data_dir=tmp_path).validate()

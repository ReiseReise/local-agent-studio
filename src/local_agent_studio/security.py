from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import os
import platform
import secrets
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol


class SecretProtectionError(RuntimeError):
    pass


class SecretBox(Protocol):
    def protect(self, value: str) -> bytes: ...

    def unprotect(self, value: bytes) -> str: ...


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class DpapiSecretBox:
    description = "Local Agent Studio secret"

    @staticmethod
    def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array]:
        buffer = ctypes.create_string_buffer(data)
        blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def protect(self, value: str) -> bytes:
        if platform.system() != "Windows":
            raise SecretProtectionError("DPAPI is available only on Windows")
        source, source_buffer = self._blob(value.encode("utf-8"))
        entropy, entropy_buffer = self._blob(b"LocalAgentStudio/v1")
        output = DATA_BLOB()
        result = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source),
            self.description,
            ctypes.byref(entropy),
            None,
            None,
            0x01,
            ctypes.byref(output),
        )
        _ = source_buffer, entropy_buffer
        if not result:
            raise SecretProtectionError("DPAPI encryption failed")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)

    def unprotect(self, value: bytes) -> str:
        if platform.system() != "Windows":
            raise SecretProtectionError("DPAPI is available only on Windows")
        source, source_buffer = self._blob(value)
        entropy, entropy_buffer = self._blob(b"LocalAgentStudio/v1")
        output = DATA_BLOB()
        result = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source),
            None,
            ctypes.byref(entropy),
            None,
            None,
            0x01,
            ctypes.byref(output),
        )
        _ = source_buffer, entropy_buffer
        if not result:
            raise SecretProtectionError("DPAPI decryption failed")
        try:
            return ctypes.string_at(output.pbData, output.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(output.pbData)


@dataclass(slots=True)
class DevelopmentSecretBox:
    """Explicit non-production envelope used only for local development and tests."""

    secret: bytes

    def _key(self) -> bytes:
        return hashlib.sha256(b"LocalAgentStudio/dev/" + self.secret).digest()

    def protect(self, value: str) -> bytes:
        nonce = secrets.token_bytes(16)
        source = value.encode("utf-8")
        key = self._key()
        stream = b"".join(
            hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
            for counter in range((len(source) // 32) + 1)
        )
        cipher = bytes(a ^ b for a, b in zip(source, stream, strict=False))
        tag = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        return b"DEV1" + nonce + tag + cipher

    def unprotect(self, value: bytes) -> str:
        if not value.startswith(b"DEV1") or len(value) < 52:
            raise SecretProtectionError("Development secret envelope is invalid")
        nonce, tag, cipher = value[4:20], value[20:52], value[52:]
        key = self._key()
        expected = hmac.new(key, nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            raise SecretProtectionError("Development secret envelope authentication failed")
        stream = b"".join(
            hashlib.sha256(key + nonce + counter.to_bytes(4, "big")).digest()
            for counter in range((len(cipher) // 32) + 1)
        )
        return bytes(a ^ b for a, b in zip(cipher, stream, strict=False)).decode("utf-8")


def make_secret_box(environment: str) -> SecretBox:
    if platform.system() == "Windows":
        return DpapiSecretBox()
    if environment not in {"development", "test"}:
        raise SecretProtectionError("Non-Windows production secret storage is not supported")
    dev_secret = os.environ.get("LAS_DEV_SECRET", "")
    if len(dev_secret) < 24:
        raise SecretProtectionError("LAS_DEV_SECRET must contain at least 24 characters in development")
    return DevelopmentSecretBox(dev_secret.encode("utf-8"))


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return (
        "scrypt$16384$8$1$"
        + base64.urlsafe_b64encode(salt).decode()
        + "$"
        + base64.urlsafe_b64encode(digest).decode()
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64)
        expected = base64.urlsafe_b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_token() -> str:
    return "las_" + secrets.token_urlsafe(32)


def opaque_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

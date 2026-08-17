from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import Database
from ..entities import SystemSetting
from ..security import SecretBox, hash_password, new_token, verify_password

ADMIN_PASSWORD_HASH = "admin_password_hash"
SESSION_SECRET = "session_secret"
CONNECTOR_TOKEN = "connector_token"
AGENT_ENABLED = "agent_enabled"


def get_setting(session: Session, key: str) -> SystemSetting | None:
    return session.get(SystemSetting, key)


def set_text_setting(session: Session, key: str, value: str) -> None:
    setting = get_setting(session, key) or SystemSetting(key=key)
    setting.value_text = value
    setting.value_secret = None
    session.add(setting)


def set_secret_setting(session: Session, key: str, value: str, secret_box: SecretBox) -> None:
    setting = get_setting(session, key) or SystemSetting(key=key)
    setting.value_text = None
    setting.value_secret = secret_box.protect(value)
    session.add(setting)


def read_secret_setting(session: Session, key: str, secret_box: SecretBox) -> str | None:
    setting = get_setting(session, key)
    if not setting or not setting.value_secret:
        return None
    return secret_box.unprotect(setting.value_secret)


def ensure_application_defaults(database: Database, secret_box: SecretBox) -> None:
    with database.session() as session:
        if not get_setting(session, SESSION_SECRET):
            set_secret_setting(session, SESSION_SECRET, secrets.token_urlsafe(48), secret_box)
        if not get_setting(session, AGENT_ENABLED):
            set_text_setting(session, AGENT_ENABLED, "true")


def session_secret(database: Database, secret_box: SecretBox) -> str:
    with database.session() as session:
        value = read_secret_setting(session, SESSION_SECRET, secret_box)
    if not value:
        raise RuntimeError("Session secret is unavailable")
    return value


def is_setup(database: Database) -> bool:
    with database.session() as session:
        return (
            session.scalar(select(SystemSetting).where(SystemSetting.key == ADMIN_PASSWORD_HASH)) is not None
        )


def complete_setup(database: Database, secret_box: SecretBox, password: str) -> str:
    password_hash = hash_password(password)
    connector_token = new_token()
    with database.session() as session:
        if get_setting(session, ADMIN_PASSWORD_HASH):
            raise ValueError("Initial setup has already been completed")
        set_text_setting(session, ADMIN_PASSWORD_HASH, password_hash)
        set_secret_setting(session, CONNECTOR_TOKEN, connector_token, secret_box)
    return connector_token


def authenticate_admin(database: Database, password: str) -> bool:
    with database.session() as session:
        setting = get_setting(session, ADMIN_PASSWORD_HASH)
        encoded = setting.value_text if setting else None
    return bool(encoded and verify_password(password, encoded))


def connector_token(database: Database, secret_box: SecretBox) -> str | None:
    with database.session() as session:
        return read_secret_setting(session, CONNECTOR_TOKEN, secret_box)


def rotate_connector_token(database: Database, secret_box: SecretBox) -> str:
    value = new_token()
    with database.session() as session:
        set_secret_setting(session, CONNECTOR_TOKEN, value, secret_box)
    return value


def agent_enabled(database: Database) -> bool:
    with database.session() as session:
        setting = get_setting(session, AGENT_ENABLED)
        return bool(setting and setting.value_text == "true")


def set_agent_enabled(database: Database, enabled: bool) -> None:
    with database.session() as session:
        set_text_setting(session, AGENT_ENABLED, "true" if enabled else "false")

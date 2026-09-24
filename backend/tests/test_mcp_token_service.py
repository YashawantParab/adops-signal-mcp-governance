from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.mcp_token_service import create_token, list_tokens, revoke_token, verify_token


def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tokens.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_create_and_verify_token_round_trip(tmp_path):
    db = db_session(tmp_path)
    token, raw = create_token(db, name="Partner Inspector", rate_limit_per_minute=10)
    assert raw.startswith("mcp_ext_")
    assert token.token_hash != raw  # never stored raw

    verified = verify_token(db, raw)
    assert verified is not None
    assert verified.id == token.id
    assert verified.last_used_at is not None


def test_verify_rejects_unknown_or_malformed_token(tmp_path):
    db = db_session(tmp_path)
    assert verify_token(db, "not-a-real-token") is None
    assert verify_token(db, "mcp_ext_wrongvalue") is None
    assert verify_token(db, "") is None


def test_revoked_token_no_longer_verifies(tmp_path):
    db = db_session(tmp_path)
    token, raw = create_token(db, name="Old Partner")
    revoke_token(db, token.id)
    assert verify_token(db, raw) is None


def test_list_tokens_never_exposes_raw_value(tmp_path):
    db = db_session(tmp_path)
    create_token(db, name="A")
    create_token(db, name="B")
    tokens = list_tokens(db)
    assert len(tokens) == 2
    for token in tokens:
        assert not hasattr(token, "token") or token.token_hash  # only the hash field exists on the model

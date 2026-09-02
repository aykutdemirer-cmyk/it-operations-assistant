"""`app/agents/authentication.py` için saf mantık testleri — gerçek ağ/DB
yok."""

from app.agents.authentication import extract_bearer_token, generate_token, hash_token


def test_generate_token_produces_high_entropy_unique_values():
    tokens = {generate_token() for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(t) >= 32 for t in tokens)


def test_hash_token_is_deterministic():
    token = generate_token()
    assert hash_token(token) == hash_token(token)


def test_hash_token_differs_for_different_tokens():
    assert hash_token("token-a") != hash_token("token-b")


def test_hash_token_never_returns_the_plaintext_token():
    token = "cok-gizli-bir-token-degeri"
    assert hash_token(token) != token
    assert token not in hash_token(token)


def test_extract_bearer_token_parses_valid_header():
    assert extract_bearer_token("Bearer abc123") == "abc123"


def test_extract_bearer_token_is_case_insensitive_for_scheme():
    assert extract_bearer_token("bearer abc123") == "abc123"


def test_extract_bearer_token_returns_none_for_missing_header():
    assert extract_bearer_token(None) is None


def test_extract_bearer_token_returns_none_for_malformed_header():
    assert extract_bearer_token("abc123") is None
    assert extract_bearer_token("Basic abc123") is None
    assert extract_bearer_token("Bearer") is None
    assert extract_bearer_token("Bearer   ") is None

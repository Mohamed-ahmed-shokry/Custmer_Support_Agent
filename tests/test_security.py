from api import security


def test_check_api_key_disabled_when_unconfigured():
    assert security.check_api_key(None, "") is True
    assert security.check_api_key("anything", "") is True


def test_check_api_key_matches_configured_key():
    assert security.check_api_key("secret", "secret") is True
    assert security.check_api_key(None, "secret") is False
    assert security.check_api_key("wrong", "secret") is False


def test_check_rate_limit_disabled_when_non_positive():
    assert security.check_rate_limit("ip", 0) is True
    assert security.check_rate_limit("ip", -1) is True


def test_check_rate_limit_allows_then_blocks():
    security.reset()
    assert security.check_rate_limit("client-a", 2, now=100.0) is True
    assert security.check_rate_limit("client-a", 2, now=101.0) is True
    assert security.check_rate_limit("client-a", 2, now=102.0) is False
    # A different client is unaffected.
    assert security.check_rate_limit("client-b", 2, now=102.0) is True


def test_check_rate_limit_window_slides():
    security.reset()
    assert security.check_rate_limit("client-c", 1, now=100.0) is True
    assert security.check_rate_limit("client-c", 1, now=150.0) is False
    assert security.check_rate_limit("client-c", 1, now=161.0) is True


def test_token_quota_disabled_when_non_positive():
    assert security.check_token_quota("ip", 10_000, 0) is True


def test_token_quota_enforces_daily_budget():
    security.reset()
    used_tokens = 60
    daily_budget = 100
    assert security.check_token_quota("ip", used_tokens, daily_budget, today="2026-09-04")
    assert (
        security.record_token_usage("ip", used_tokens, today="2026-09-04") == used_tokens
    )
    assert security.check_token_quota("ip", 40, daily_budget, today="2026-09-04")
    assert not security.check_token_quota("ip", 41, daily_budget, today="2026-09-04")
    # Usage resets on a new day and is tracked per client.
    assert security.check_token_quota("ip", 100, 100, today="2026-09-05") is True
    assert security.check_token_quota("other", 100, 100, today="2026-09-04") is True


def test_public_paths_cover_probes_metrics_and_docs():
    for path in (
        "/health",
        "/health/live",
        "/health/ready",
        "/metrics",
        "/metrics.json",
        "/docs",
        "/openapi.json",
    ):
        assert security.is_public_path(path) is True
    assert security.is_public_path("/chat") is False
    assert security.is_public_path("/upload-doc") is False

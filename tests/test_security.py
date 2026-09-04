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

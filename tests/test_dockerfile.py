from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _copy_sources(dockerfile: str):
    sources = []
    for raw_line in dockerfile.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("COPY"):
            continue
        tokens = line.split()
        if any(token.startswith("--from=") for token in tokens):
            continue
        sources.extend(tokens[1:-1])
    return sources


def test_dockerfile_copy_sources_exist():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    sources = _copy_sources(dockerfile)

    assert sources, "Dockerfile must have COPY instructions"
    for source in sources:
        path = source.rstrip("/")
        if any(char in path for char in "*?"):
            continue
        assert (REPO_ROOT / path).exists(), f"Dockerfile COPY source missing: {source}"


def test_dockerfile_does_not_copy_deleted_pytest_ini():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "pytest.ini" not in dockerfile
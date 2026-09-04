"""Manual retrieval eval: checks golden questions against the live vector store.

Usage (requires OPENAI_API_KEY and an indexed corpus):
    python scripts/eval_retrieval.py [--golden docs/eval/golden.json]

Exit code is 0 when every case retrieves its expected file in the top-k
chunks, 1 otherwise. Not run in CI (needs API credits and local data).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.chroma_utils import get_vectorstore
from api.settings import settings


def evaluate(golden_path: Path) -> int:
    dataset = json.loads(golden_path.read_text(encoding="utf-8"))
    vectorstore = get_vectorstore()
    failures = 0
    for case in dataset["cases"]:
        k = int(case.get("k", settings.retriever_k))
        docs = vectorstore.similarity_search(case["question"], k=k)
        retrieved = {(d.metadata or {}).get("filename") for d in docs}
        expected = case["expected_filename"]
        passed = expected in retrieved
        status = "PASS" if passed else "FAIL"
        print(
            f"[{status}] {case['id']}: expected {expected!r}, "
            f"got {sorted(name or '' for name in retrieved)}"
        )
        failures += 0 if passed else 1
    print(f"{len(dataset['cases']) - failures}/{len(dataset['cases'])} cases passed")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the golden retrieval eval set.")
    parser.add_argument("--golden", default="docs/eval/golden.json")
    args = parser.parse_args(argv)
    return evaluate(Path(args.golden))


if __name__ == "__main__":
    raise SystemExit(main())

"""Manual retrieval eval: checks golden questions against the live vector store.

Usage (requires OPENAI_API_KEY and an indexed corpus):
    python scripts/eval_retrieval.py [--golden docs/eval/golden.json]
    python scripts/eval_retrieval.py --expand [--count 3]
    python scripts/eval_retrieval.py --compare

``--compare`` runs every case twice (plain vector search vs query expansion)
so recall changes can be judged before enabling ``USE_QUERY_EXPANSION``.
Exit code is 0 when every evaluated case passes, 1 otherwise.
Not run in CI (needs API credits and local data).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from api.chroma_utils import get_vectorstore
from api.expansion import reciprocal_rank_fuse, rewrite_queries
from api.settings import settings


def retrieve_filenames(  # noqa: PLR0913, PLR0917 - explicit eval options
    vectorstore, question, k, expand=False, llm=None, count=3
):
    """Return the set of filenames in the top-k chunks for a question."""
    if not expand:
        docs = vectorstore.similarity_search(question, k=k)
    else:
        variants = rewrite_queries(question, llm=llm, count=count)
        ranked = [vectorstore.similarity_search(variant, k=k) for variant in variants]
        docs = reciprocal_rank_fuse(ranked, k)
    return {(doc.metadata or {}).get("filename") for doc in docs}


def evaluate_case(  # noqa: PLR0913, PLR0917 - explicit eval options
    vectorstore, case, k, expand=False, llm=None, count=3
):
    """Evaluate one golden case, returning (passed, retrieved_filenames)."""
    retrieved = retrieve_filenames(vectorstore, case["question"], k, expand, llm, count)
    return case["expected_filename"] in retrieved, retrieved


def _report(case_id, expected, retrieved, mode):
    status = "PASS" if expected in retrieved else "FAIL"
    print(
        f"[{status}] {case_id} ({mode}): expected {expected!r}, "
        f"got {sorted(name or '' for name in retrieved)}"
    )
    return status == "PASS"


def evaluate(golden_path: Path, expand=False, compare=False, count=3, llm=None) -> int:
    dataset = json.loads(golden_path.read_text(encoding="utf-8"))
    vectorstore = get_vectorstore()
    modes = ("baseline", "expanded") if compare else ("expanded" if expand else ("baseline",))
    totals = dict.fromkeys(modes, 0)
    for case in dataset["cases"]:
        k = int(case.get("k", settings.retriever_k))
        for mode in modes:
            passed, retrieved = evaluate_case(
                vectorstore, case, k, expand=(mode == "expanded"), llm=llm, count=count
            )
            _report(case["id"], case["expected_filename"], retrieved, mode)
            totals[mode] += passed
    total = len(dataset["cases"])
    for mode in modes:
        print(f"{totals[mode]}/{total} {mode} cases passed")
    return 0 if all(value == total for value in totals.values()) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the golden retrieval eval set.")
    parser.add_argument("--golden", default="docs/eval/golden.json")
    parser.add_argument("--expand", action="store_true", help="use query expansion")
    parser.add_argument("--compare", action="store_true", help="run baseline and expanded")
    parser.add_argument("--count", type=int, default=3, help="query variants when expanding")
    args = parser.parse_args(argv)
    return evaluate(Path(args.golden), expand=args.expand, compare=args.compare, count=args.count)


if __name__ == "__main__":
    raise SystemExit(main())

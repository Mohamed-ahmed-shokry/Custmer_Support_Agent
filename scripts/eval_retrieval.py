"""Manual retrieval eval: checks golden questions against the live vector store.

Usage (requires OPENAI_API_KEY and an indexed corpus):
    python scripts/eval_retrieval.py [--golden docs/eval/golden.json]
    python scripts/eval_retrieval.py --expand [--count 3]
    python scripts/eval_retrieval.py --hybrid
    python scripts/eval_retrieval.py --rerank
    python scripts/eval_retrieval.py --collection leases
    python scripts/eval_retrieval.py --compare
    python scripts/eval_retrieval.py --json-output eval_results.json

``--compare`` runs every case twice (plain vector search vs configured enhanced strategy)
so recall changes can be judged before enabling runtime flags.
Exit code is 0 when every evaluated case passes, 1 otherwise.
Not run in CI (needs API credits and local data).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from api.chroma_utils import get_hybrid_retriever, get_vectorstore
from api.expansion import reciprocal_rank_fuse, rewrite_queries
from api.rerank import rerank_by_term_overlap
from api.settings import settings

CANDIDATE_RERANK_MULTIPLIER = 3


def retrieve_filenames(  # noqa: PLR0913, PLR0917 - explicit eval options
    vectorstore: Any,
    question: str,
    k: int,
    expand: bool = False,
    llm: Any = None,
    count: int = 3,
    hybrid: bool = False,
    rerank: bool = False,
    collection: str | None = None,
) -> set[str | None]:
    """Return the set of filenames in the top-k chunks for a question."""
    candidate_k = k * CANDIDATE_RERANK_MULTIPLIER if rerank else k
    search_kwargs: dict[str, Any] = {}
    if collection:
        search_kwargs["filter"] = {"collection": {"$in": [collection]}}

    if hybrid:
        if hasattr(vectorstore, "hybrid_search"):
            docs = vectorstore.hybrid_search(question, k=candidate_k, collection=collection)
        else:
            try:
                retriever = get_hybrid_retriever(
                    k=candidate_k, collections=[collection] if collection else None
                )
                docs = retriever.invoke(question)
            except Exception:
                docs = vectorstore.similarity_search(question, k=candidate_k, **search_kwargs)
    elif expand:
        variants = rewrite_queries(question, llm=llm, count=count)
        ranked = [
            vectorstore.similarity_search(variant, k=candidate_k, **search_kwargs)
            for variant in variants
        ]
        docs = reciprocal_rank_fuse(ranked, candidate_k)
    elif search_kwargs:
        try:
            docs = vectorstore.similarity_search(question, k=candidate_k, **search_kwargs)
        except TypeError:
            docs = vectorstore.similarity_search(question, k=candidate_k)
    else:
        docs = vectorstore.similarity_search(question, k=candidate_k)

    if collection:
        docs = [d for d in docs if not d.metadata or d.metadata.get("collection") == collection]

    if rerank:
        docs = rerank_by_term_overlap(question, docs, top_n=k)

    return {(doc.metadata or {}).get("filename") for doc in docs}


def evaluate_case(  # noqa: PLR0913, PLR0917 - explicit eval options
    vectorstore: Any,
    case: dict[str, Any],
    k: int,
    expand: bool = False,
    llm: Any = None,
    count: int = 3,
    hybrid: bool = False,
    rerank: bool = False,
    collection: str | None = None,
) -> tuple[bool, set[str | None]]:
    """Evaluate one golden case, returning (passed, retrieved_filenames)."""
    retrieved = retrieve_filenames(
        vectorstore,
        case["question"],
        k,
        expand=expand,
        llm=llm,
        count=count,
        hybrid=hybrid,
        rerank=rerank,
        collection=collection or case.get("collection"),
    )
    return case["expected_filename"] in retrieved, retrieved


def _report(case_id: str, expected: str, retrieved: set[str | None], mode: str) -> bool:
    status = "PASS" if expected in retrieved else "FAIL"
    print(
        f"[{status}] {case_id} ({mode}): expected {expected!r}, "
        f"got {sorted(name or '' for name in retrieved)}"
    )
    return status == "PASS"


def _determine_modes(
    compare: bool, expand: bool, hybrid: bool, rerank: bool
) -> tuple[str, ...]:
    if compare:
        enhanced_parts: list[str] = []
        if expand:
            enhanced_parts.append("expanded")
        if hybrid:
            enhanced_parts.append("hybrid")
        if rerank:
            enhanced_parts.append("reranked")
        enhanced_mode = "+".join(enhanced_parts) if enhanced_parts else "expanded"
        return ("baseline", enhanced_mode)

    parts: list[str] = []
    if expand:
        parts.append("expanded")
    if hybrid:
        parts.append("hybrid")
    if rerank:
        parts.append("reranked")
    return ("+".join(parts),) if parts else ("baseline",)


def evaluate(  # noqa: PLR0913, PLR0917 - explicit eval options
    golden_path: Path,
    expand: bool = False,
    compare: bool = False,
    count: int = 3,
    llm: Any = None,
    hybrid: bool = False,
    rerank: bool = False,
    collection: str | None = None,
    json_output: Path | None = None,
) -> int:
    dataset = json.loads(golden_path.read_text(encoding="utf-8"))
    vectorstore = get_vectorstore()
    modes = _determine_modes(compare=compare, expand=expand, hybrid=hybrid, rerank=rerank)
    totals = dict.fromkeys(modes, 0)
    case_records: list[dict[str, Any]] = []

    for case in dataset["cases"]:
        k = int(case.get("k", settings.retriever_k))
        case_result: dict[str, Any] = {
            "id": case.get("id"),
            "question": case.get("question"),
            "expected_filename": case.get("expected_filename"),
            "collection": collection or case.get("collection"),
            "modes": {},
        }
        for mode in modes:
            is_baseline = mode == "baseline"
            mode_expand = (
                False
                if is_baseline
                else (expand or (compare and not hybrid and not rerank))
            )
            mode_hybrid = False if is_baseline else hybrid
            mode_rerank = False if is_baseline else rerank
            passed, retrieved = evaluate_case(
                vectorstore,
                case,
                k,
                expand=mode_expand,
                llm=llm,
                count=count,
                hybrid=mode_hybrid,
                rerank=mode_rerank,
                collection=collection,
            )
            _report(case["id"], case["expected_filename"], retrieved, mode)
            totals[mode] += int(passed)
            case_result["modes"][mode] = {
                "passed": passed,
                "retrieved": sorted(name or "" for name in retrieved),
            }
        case_records.append(case_result)

    total = len(dataset["cases"])
    summary_modes: dict[str, dict[str, Any]] = {}
    for mode in modes:
        passed_count = totals[mode]
        pass_rate = (passed_count / total) if total > 0 else 0.0
        summary_modes[mode] = {"passed": passed_count, "total": total, "pass_rate": pass_rate}
        print(f"{passed_count}/{total} {mode} cases passed ({pass_rate:.1%})")

    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "summary": {"total_cases": total, "modes": summary_modes},
            "results": case_records,
        }
        json_output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Eval report written to {json_output}")

    return 0 if all(value == total for value in totals.values()) else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the golden retrieval eval set.")
    parser.add_argument("--golden", default="docs/eval/golden.json")
    parser.add_argument("--expand", action="store_true", help="use query expansion")
    parser.add_argument("--hybrid", action="store_true", help="use hybrid BM25 + vector search")
    parser.add_argument("--rerank", action="store_true", help="use term-overlap reranking")
    parser.add_argument(
        "--collection", type=str, default=None, help="scope retrieval to a collection"
    )
    parser.add_argument(
        "--compare", action="store_true", help="run baseline vs configured enhanced strategy"
    )
    parser.add_argument("--count", type=int, default=3, help="query variants when expanding")
    parser.add_argument(
        "--json-output", type=str, default=None, help="path to write JSON eval report"
    )
    args = parser.parse_args(argv)
    json_path = Path(args.json_output) if args.json_output else None
    return evaluate(
        Path(args.golden),
        expand=args.expand,
        compare=args.compare,
        count=args.count,
        hybrid=args.hybrid,
        rerank=args.rerank,
        collection=args.collection,
        json_output=json_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())

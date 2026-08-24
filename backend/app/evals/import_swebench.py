"""Create a transparent organic benchmark manifest from official SWE-bench rows."""

import argparse
import hashlib
import json
import random
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_SOURCE = "https://datasets-server.huggingface.co/rows?" + urllib.parse.urlencode(
    {
        "dataset": "SWE-bench/SWE-bench_Verified",
        "config": "default",
        "split": "test",
        "offset": 0,
        "length": 100,
    }
)


def _load_source(source: str) -> tuple[bytes, object]:
    path = Path(source)
    if path.exists():
        data = path.read_bytes()
        return data, json.loads(data)
    parsed = urllib.parse.urlparse(source)
    query = urllib.parse.parse_qs(parsed.query)
    page_size = min(int(query.get("length", [100])[0]), 100)
    offset = int(query.get("offset", [0])[0])
    collected = []
    total = None
    while total is None or offset < total:
        query["offset"] = [str(offset)]
        query["length"] = [str(page_size)]
        page_url = urllib.parse.urlunparse(
            parsed._replace(query=urllib.parse.urlencode(query, doseq=True))
        )
        request = urllib.request.Request(
            page_url, headers={"User-Agent": "autonomous-swe-agent"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            page = json.loads(response.read())
        rows = page.get("rows", [])
        collected.extend(rows)
        total = int(page.get("num_rows_total") or len(collected))
        if not rows:
            break
        offset += len(rows)
    payload = {"rows": collected, "num_rows_total": total}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return data, payload


def _rows(payload: object) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [item.get("row", item) for item in payload["rows"]]
    if isinstance(payload, list):
        return payload
    raise ValueError("unsupported SWE-bench source payload")


def _list_field(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def select_rows(
    rows: list[dict],
    *,
    size: int,
    seed: int,
    max_per_repository: int,
    min_multifile: int = 0,
) -> list[dict]:
    candidates = [
        row
        for row in rows
        if row.get("instance_id")
        and row.get("repo")
        and row.get("base_commit")
        and row.get("problem_statement")
        and row.get("patch")
        and row.get("test_patch")
    ]
    rng = random.Random(seed)
    rng.shuffle(candidates)
    counts: Counter[str] = Counter()
    selected = []
    multifile = [row for row in candidates if _patch_file_count(str(row["patch"])) > 1]
    remainder = [row for row in candidates if row not in multifile]
    for pool, target in ((multifile, min_multifile), (remainder + multifile, size)):
        for row in pool:
            if len(selected) >= target:
                break
            repository = str(row["repo"])
            if row in selected or counts[repository] >= max_per_repository:
                continue
            counts[repository] += 1
            selected.append(row)
    if len(selected) != size:
        raise ValueError(
            f"source only yielded {len(selected)} eligible rows; requested {size} "
            f"with max {max_per_repository} per repository"
        )
    actual_multifile = sum(_patch_file_count(str(row["patch"])) > 1 for row in selected)
    if actual_multifile < min_multifile:
        raise ValueError(
            f"source only yielded {actual_multifile} balanced multi-file rows; "
            f"requested at least {min_multifile}"
        )
    return sorted(selected, key=lambda row: str(row["instance_id"]))


def _patch_file_count(patch: str) -> int:
    files = {
        line.split(" b/", 1)[0].removeprefix("diff --git a/")
        for line in patch.splitlines()
        if line.startswith("diff --git a/") and " b/" in line
    }
    return len(files)


def convert_row(row: dict) -> dict:
    instance_id = str(row["instance_id"])
    repository = str(row["repo"])
    pull_number = instance_id.rsplit("-", 1)[-1]
    test_patch = str(row["test_patch"])
    patch_file_count = _patch_file_count(str(row["patch"]))
    return {
        "case_id": instance_id,
        "task_key": instance_id,
        "repository": f"https://github.com/{repository}.git",
        "source_commit": str(row["base_commit"]),
        "base_branch": "main",
        "prompt": str(row["problem_statement"]),
        "test_command": "git diff --check",
        "max_iterations": 3,
        "tags": [
            "organic",
            "swe-bench-verified",
            "multi-file" if patch_file_count > 1 else "single-file",
            f"repo:{repository}",
        ],
        "experiment_variant": "full",
        "provenance": "swe-bench-verified",
        "source_url": f"https://github.com/{repository}/pull/{pull_number}",
        "swebench_instance_id": instance_id,
        "requires_hidden_evaluation": True,
        "evaluation_patch_sha256": hashlib.sha256(test_patch.encode()).hexdigest(),
        "fail_to_pass": _list_field(row.get("FAIL_TO_PASS")),
        "pass_to_pass": _list_field(row.get("PASS_TO_PASS")),
        "gold_patch_file_count": patch_file_count,
        "task_scope": "multi_file" if patch_file_count > 1 else "single_file",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a balanced SWE-bench Verified subset")
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-per-repository", type=int, default=6)
    parser.add_argument("--min-multifile", type=int, default=15)
    args = parser.parse_args()

    source_bytes, payload = _load_source(args.source)
    selected = select_rows(
        _rows(payload),
        size=args.size,
        seed=args.seed,
        max_per_repository=args.max_per_repository,
        min_multifile=args.min_multifile,
    )
    converted = [convert_row(row) for row in selected]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in converted),
        encoding="utf-8",
    )
    repository_counts = Counter(row["repository"] for row in converted)
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "source": args.source,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "selection_seed": args.seed,
        "size": len(converted),
        "max_per_repository": args.max_per_repository,
        "minimum_multifile_tasks": args.min_multifile,
        "multifile_tasks": sum(row["task_scope"] == "multi_file" for row in converted),
        "repositories": dict(sorted(repository_counts.items())),
        "contains_gold_patch": False,
        "contains_test_patch": False,
        "note": "Hidden tests are applied only by the official SWE-bench harness.",
    }
    metadata_path = args.output.with_suffix(".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""SWE-bench manifest importer tests."""

import json
from pathlib import Path

from app.evals.import_swebench import convert_row, select_rows


def _row(index: int, repository: str) -> dict:
    return {
        "instance_id": f"{repository.replace('/', '__')}-{index}",
        "repo": repository,
        "base_commit": f"{index:040x}",
        "problem_statement": f"Real issue {index}",
        "test_patch": f"hidden test patch {index}",
        "patch": (
            "diff --git a/a.py b/a.py\n"
            + ("diff --git a/b.py b/b.py\n" if index % 2 == 0 else "")
        ),
        "FAIL_TO_PASS": [f"test_{index}"],
        "PASS_TO_PASS": [],
    }


def test_select_rows_balances_repositories_deterministically():
    rows = [_row(index, f"owner/repo-{index % 3}") for index in range(12)]
    selected = select_rows(
        rows, size=6, seed=42, max_per_repository=2, min_multifile=3
    )
    assert selected == select_rows(
        rows, size=6, seed=42, max_per_repository=2, min_multifile=3
    )
    counts = {}
    for row in selected:
        counts[row["repo"]] = counts.get(row["repo"], 0) + 1
    assert counts == {"owner/repo-0": 2, "owner/repo-1": 2, "owner/repo-2": 2}


def test_convert_row_excludes_gold_and_hidden_patch_contents():
    converted = convert_row(_row(7, "owner/repository"))
    assert converted["provenance"] == "swe-bench-verified"
    assert converted["requires_hidden_evaluation"] is True
    assert len(converted["evaluation_patch_sha256"]) == 64
    assert "patch" not in converted
    assert "test_patch" not in converted
    assert converted["test_command"] == "git diff --check"
    assert converted["gold_patch_file_count"] == 1


def test_committed_verified_manifest_meets_acceptance_criteria():
    dataset = Path("evals/datasets/organic-swebench-verified-v1.jsonl")
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]

    assert len(rows) == 30
    assert len({row["repository"] for row in rows}) >= 5
    assert sum(row["task_scope"] == "multi_file" for row in rows) >= 15
    assert max(
        sum(candidate["repository"] == row["repository"] for candidate in rows)
        for row in rows
    ) <= 6
    assert all("patch" not in row and "test_patch" not in row for row in rows)

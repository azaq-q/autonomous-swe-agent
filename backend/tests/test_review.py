"""Structured Review Agent output parsing tests."""

from app.agents.review import ReviewAgent


def test_parse_valid_review_json():
    result = ReviewAgent._parse(
        '{"verdict":"approve","summary":"looks good","issues":[]}'
    )
    assert result.verdict == "approve"
    assert result.issues == []


def test_invalid_review_output_fails_closed():
    result = ReviewAgent._parse("not json")
    assert result.verdict == "request_changes"
    assert result.issues[0].severity == "medium"

from typing import get_args

import pytest
from coday_contracts.review_result import Finding
from coday_pipeline.act.markdown import BADGE_BASE_URL, render_review_badges

SEVERITIES = {"Critical": "critical", "High": "high", "Medium": "medium", "Low": "low"}
CATEGORIES = {
    "bug": "Bug",
    "security": "Security",
    "performance": "Performance",
    "maintainability": "Maintainability",
    "style": "Style",
}


def test_badges_cover_finding_contract():
    assert set(SEVERITIES) == set(get_args(Finding.model_fields["severity"].annotation))
    assert set(CATEGORIES) == set(get_args(Finding.model_fields["category"].annotation))


@pytest.mark.parametrize("severity,prefix", SEVERITIES.items())
@pytest.mark.parametrize("category,label", CATEGORIES.items())
def test_renders_both_themes_and_light_fallback(severity, prefix, category, label):
    assert BADGE_BASE_URL == (
        "https://raw.githubusercontent.com/CO-DAY-TEAM/CO-DAY/main/assets/badges"
    )
    expected = []
    for group, name, alt in (("severity", prefix, severity), ("category", category, label)):
        root = f"{BADGE_BASE_URL}/{group}/{name}"
        expected.append(
            f'<picture><source media="(prefers-color-scheme: dark)" srcset="{root}-dark.svg">'
            f'<source media="(prefers-color-scheme: light)" srcset="{root}-light.svg">'
            f'<img src="{root}-light.svg" alt="{alt}" height="18" align="texttop"></picture>'
        )
    assert render_review_badges(severity, category, base_url=f"{BADGE_BASE_URL}/") == " ".join(
        expected
    )


@pytest.mark.parametrize(("severity", "category"), [("high", "bug"), ("High", "../bug")])
def test_rejects_unknown_contract_values(severity, category):
    with pytest.raises(ValueError):
        render_review_badges(severity, category)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "/assets",
        "https:///assets",
        "https://user:token@example.org",
        "https://example.org/a?",
        "https://example.org/a#",
        "https://example.org/a b",
        "https://example.org/a\nb",
        'https://example.org/a"b',
        "https://example.org/a,b",
        "https://example..org",
        "https://example.org:99999",
    ],
)
def test_rejects_invalid_urls(url):
    with pytest.raises(ValueError):
        render_review_badges("High", "bug", base_url=url)


def test_escapes_url_attributes():
    html = render_review_badges("Low", "style", base_url="https://example.org/a&b")
    assert html.count("/a&amp;b/") == 6

from coday_contracts import ReviewInput


def test_review_input_pr_metadata_round_trip():
    title = "리뷰 컨텍스트 추가"
    body = "## 변경 목적\n\nPR의 배경을 전달합니다."
    review_input = ReviewInput(pr_title=title, pr_body=body)

    assert review_input.pr_title == title
    assert review_input.pr_body == body
    assert ReviewInput.model_validate_json(review_input.model_dump_json()) == review_input


def test_review_input_pr_metadata_defaults_to_empty_strings():
    review_input = ReviewInput()

    assert review_input.pr_title == ""
    assert review_input.pr_body == ""

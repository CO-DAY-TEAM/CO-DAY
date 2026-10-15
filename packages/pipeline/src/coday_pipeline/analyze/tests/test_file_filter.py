from coday_contracts.settings import ReviewSettings
from coday_pipeline.analyze.file_filter import exclusion


# 소스 파일은 유지하고 lockfile과 의존성 디렉터리는 리뷰 대상에서 제외하는지 확인한다.
def test_filter_keeps_source_and_excludes_lockfiles_and_dependencies():
    settings = ReviewSettings()
    assert exclusion("src/clock.py", settings.exclude_patterns) is None
    assert exclusion("package-lock.json", settings.exclude_patterns)
    assert exclusion("node_modules/x/index.js", settings.exclude_patterns)

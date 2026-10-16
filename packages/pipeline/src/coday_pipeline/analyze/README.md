# analyze

### 1. 폴더 구조 세분화
- 수집 → 필터링 → diff 파싱 → 청크 분할의 흐름
- 장점: 파일마다 하는 일이 하나라 읽기 쉬움

```
analyze/
├── __init__.py        # 공개: analyze 하나만
├── service.py         # 진입 함수 analyze(): 순서대로 호출만
├── diff_parser.py     # patch 문자열 → hunk와 줄 번호
├── file_filter.py     # 리뷰할 파일인지 판단
├── chunker.py         # hunk → AnalyzedChunk 목록
└── tests/
    ├── test_diff_parser.py
    ├── test_file_filter.py
    └── test_service.py
```

### 2. `service.py`에 넣지 말아야 할 것

- **GitHub API 호출 코드를 직접 작성하기**: HTTP 요청 같은 공통 인프라는 `coday_core/github.py`에 두고, `service.py`는 가져다 쓰기만 합니다.
- **다른 단계 호출**: `analyze()` 안에서 `judge()`를 부르면 안 됩니다. 단계를 잇는 건 워커의 몫입니다.
- **dict를 그대로 주고받기**: 단계 바깥과 주고받는 데이터는 반드시 `contracts` 스키마로 합니다.
- **`if __name__ == "__main__":` 실행 코드**: 수동 실행은 `scripts/`에 따로 만듭니다.

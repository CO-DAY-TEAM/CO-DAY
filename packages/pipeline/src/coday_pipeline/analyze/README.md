# analyze

### 1. 폴더 구조 세분화
- 수집 → 필터링 → diff 파싱·검증 → 전체 PR 입력 구성의 흐름
- 장점: 파일마다 하는 일이 하나라 읽기 쉬움

```
analyze/
├── __init__.py        # 공개: analyze 하나만
├── service.py         # 진입 함수 analyze(): 수집·파싱·검증·입력 구성
├── collector.py       # GitHub PR patch와 관련 코드 수집
├── diff_parser.py     # patch 문자열 → hunk와 줄 번호
├── file_filter.py     # 리뷰할 파일인지 판단
└── tests/
    ├── test_diff_parser.py
    └── test_file_filter.py
```

Analyze에서 파싱한 hunk와 줄 정보를 파일별로 묶어 Judge에 전달합니다.

### 2. `service.py`에 넣지 말아야 할 것

- **GitHub API 호출 코드를 직접 작성하기**: HTTP 요청 같은 공통 인프라는 `coday_core/github.py`에 두고, `service.py`는 가져다 쓰기만 합니다.
- **다른 단계 호출**: `analyze()` 안에서 `judge()`를 부르면 안 됩니다. 단계를 잇는 건 워커의 몫입니다.
- **dict를 그대로 주고받기**: 단계 바깥과 주고받는 데이터는 반드시 `contracts` 스키마로 합니다.
- **`if __name__ == "__main__":` 실행 코드**: 수동 실행은 `scripts/`에 따로 만듭니다.

### 3. 문맥 수집과 지원 범위

- 직접 로컬 import, 명시적인 JS/TS 경로 별칭, 같은 저장소의 Helm·Argo 참조를 활용해 관련 파일을 수집합니다.
- Python·JS/TS(JSX·TSX 포함)의 변경 함수 문맥을 보완하고, diff에 이미 있는 코드는 중복 전달하지 않습니다.
- 관련 파일과 함수 문맥에 파일 수·파일 크기·전체 입력 예산 및 제외 규칙을 적용합니다. 미지원 언어, 파싱 실패, 예산 초과 등으로 보완 문맥이 제외될 수 있습니다.
- 외부 저장소·외부 패키지, 계산된 경로, 모호한 참조, 재귀적인 호출 대상 추적은 지원하지 않습니다. Go import와 CSS 변수 정의 탐색도 포함하지 않습니다.
- ReviewBench도 공통 참조 해석·관련 파일 선정·함수 문맥 수집 로직을 사용합니다.

### 4. 입출력과 진단 정보

`analyze()`는 `ReviewJob`, 리뷰 설정과 GitHub 접근에 필요한 의존성을 받아,
변경 파일의 hunk·줄 정보, 제외 파일, 관련 파일 본문과 함수 문맥을 `ReviewInput`으로 반환합니다.

문맥 수집 진단 정보는 수집기 내부에서 관리하며 `ReviewInput`에 포함하지 않습니다.
운영에서는 진단 정보가 있을 때 로그로 출력하고, ReviewBench에서는 `raw-review.json`에 별도로 기록합니다.

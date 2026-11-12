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


관련 파일은 변경 줄에 이름이 나타나는 직접 로컬 import, 그 밖의 직접 로컬 import,
기존 파일명 유사도, 같은 디렉터리 순으로 선정합니다. 이름 참조는 정적 식별자 비교이며
정확한 호출 그래프나 심벌 해석을 보장하지 않습니다.
Python은 AST와 실제 패키지 경로를, JS/TS는 정적 상대 import와 literal require를 사용합니다.
외부 패키지·설정 기반 별칭·동적 import·모호한 확장자 해석은 추측하지 않습니다.
변경 파일의 PR HEAD 원문을 제한 내에서 읽어 import를 확인하지만 이 원문을 리뷰 입력에
추가하지는 않습니다. 관련 파일의 전체 본문 전달, 최대 5개 기본값, 제외 규칙과 크기 한도는 유지합니다.
ReviewBench 어댑터도 동일한 경로 해석·우선순위 함수를 사용합니다.

Helm chart의 values/템플릿 변경과, 변경된 Argo Application/ApplicationSet의 명시적인
`source.path`·`helm.valueFiles` 연결도 관련 템플릿 선정에 사용합니다. 같은 저장소임이
확인되는 참조만 따라가며 디렉터리 생성기는 `.path.basename`·`.path.path` 치환만 지원합니다.
외부 저장소, `$values`, 알 수 없는 템플릿 변수·generator 제외 조건은 추측하지 않습니다.
삭제된 values도 변경 경로와 대조할 수 있지만 순수 rename의 검토 범위는 확장하지 않습니다.

기본 관련 문맥 5개·파일당 18,000바이트 제한은 유지합니다. 변경 patch의 바이트를 먼저
예약하고 남은 입력 예산에 맞는 후보를 선정합니다. 빈 파일은 제외하며, 읽은 내용이
비텍스트/크기 초과이면 다른 후보로 보충하되 관련 본문 읽기는 파일 수 제한의 2배 이내입니다.
운영 collector와 평가 어댑터는 같은 참조 해석·순위 함수를 사용합니다.
이번 단계는 파일 선정 개선이며 함수 구간 추출, Go import, CSS 변수 정의 탐색은 포함하지 않습니다.

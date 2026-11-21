# 코드 리뷰 SVG 뱃지

[PR-BOT-TEST `dev`의 원본 SVG](https://github.com/choyekyo/PR-BOT-TEST/tree/28fe649f46a1608e6b46f91e82ab364a88c41289/assets/badges)를 가져왔습니다. 각 이름에 `-light.svg`, `-dark.svg`를 붙여 테마별 파일을 참조합니다.

| 경로 | 파일명 접두어 |
| --- | --- |
| `assets/badges/severity/` | `critical`, `high`, `medium`, `low` |
| `assets/badges/category/` | `bug`, `security`, `performance`, `maintainability`, `style` |

## Act에서 참조하는 방법

`main`에 병합되면 공개 저장소의 GitHub Raw URL로 제공됩니다. 별도 배포 설정은 필요하지 않습니다.

```text
https://raw.githubusercontent.com/CO-DAY-TEAM/CO-DAY/main/assets/badges/{severity|category}/{name}-{light|dark}.svg
```

뱃지마다 `<picture>`를 사용합니다. 다크 `<source media="(prefers-color-scheme: dark)">`의 `srcset`에는 다크 URL을, 라이트 `<source media="(prefers-color-scheme: light)">`의 `srcset`에는 라이트 URL을 지정합니다. 기본 `<img>`에는 라이트 URL, 뱃지 이름을 담은 `alt`, `height="18"`을 지정합니다. Severity를 먼저 두고 같은 줄에 공백 하나로 Category를 연결합니다.

리뷰 댓글에 적용하는 작업은 Issue #64에서 진행합니다.

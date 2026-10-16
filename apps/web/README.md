# CO-DAY 대시보드

React·TypeScript·Vite로 구현한 대시보드입니다. GitHub 로그인, 저장소 연결, 공통·저장소별 설정, 리뷰 목록, 실패 재시도와 통계를 제공합니다. 화면의 설명은 한국어로 작성하고, GitHub 권한명과 코드 식별자는 원문을 사용합니다.

## 개발 실행

CO-DAY 폴더에서 실행합니다.

```bash
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web dev
```

Vite는 `/api` 요청을 `http://127.0.0.1:8000`의 FastAPI 서버로 전달합니다. API·Worker 실행과 GitHub App 연결은 [프로젝트 실행 안내](../../README.md)를 따릅니다.

## 정적 검사와 빌드

```bash
pnpm --dir apps/web lint
pnpm --dir apps/web build
```

`lint`는 Oxlint를 실행합니다. `build`는 TypeScript 검사 후 Vite로 빌드하며, 결과는 `dist/`에 생성됩니다. 빌드된 화면은 FastAPI 서버에서 제공합니다.

제품 동작과 완료 기준은 [최종 설계](../../docs/github-app-design.md)를 따릅니다.

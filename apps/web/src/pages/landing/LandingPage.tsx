import { Logo } from '../../components/Logo'
import './LandingPage.css'

export function LandingPage({ error }: { error: string }) {
  return (
    <main className="landing">
      <header className="landing-nav">
        <Logo />
        <span className="tag">AI 코드 리뷰</span>
        <span className="title-path">guest@co-day: ~/welcome</span>
      </header>
      <div className="landing-grid">
        <section className="hero">
          <div className="boot-line">
            <span className="accent">›</span> 코드를 함께 읽는 또 하나의 동료
            <span className="cursor">▍</span>
          </div>
          <h1 className="hero-title">
            리뷰는 GitHub에서.
            <br />
            <strong>팀의 기준은 여기서.</strong>
          </h1>
          <p>
            PR의 변경 사항을 살펴보고, 근거 있는 리뷰와
            <br className="desktop-break" /> 바로 적용할 수 있는 수정 제안을
            전합니다.
          </p>
          <a
            className="button primary login-button"
            href={`/api/auth/login?return_to=${encodeURIComponent('/' + window.location.search)}`}
          >
            GitHub로 시작하기 ↗
          </a>
          <div className="login-message" role="alert">
            {error && `✖ ${error}`}
          </div>
        </section>
        <div className="landing-terminal" aria-label="CO-DAY 리뷰 실행 예시">
          <div className="mini-title">
            <span className="traffic" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <code>co-day review --example</code>
          </div>
          <div className="terminal-body">
            <p>
              <span className="accent">$</span> co-day review{' '}
              <span className="muted">--pr=128</span>
            </p>
            <p className="muted">⠹ 변경된 파일을 읽고 있습니다...</p>
            <p>
              <span className="accent">✔</span> 12 files analyzed
            </p>
            <p>
              <span className="warning">▲ WARN</span> SQL query requires
              validation
            </p>
            <p className="code-line">
              <span>42</span> const user = await db.query(input);
            </p>
            <p>
              <span className="info">→ FIX</span> parameterized query 사용을
              제안합니다.
            </p>
            <div className="terminal-progress">
              <i />
            </div>
            <small className="accent">████████████ 12/12 · review complete</small>
          </div>
        </div>
      </div>
      <section className="features" aria-label="주요 기능">
        <div>
          <b>01</b>
          <span>PR 자동 리뷰</span>
          <p>변경 맥락을 읽고 이슈와 수정안을 제안합니다.</p>
        </div>
        <div>
          <b>02</b>
          <span>팀별 리뷰 설정</span>
          <p>팀의 기준과 제외 경로에 맞춰 리뷰 방식을 조정합니다.</p>
        </div>
        <div>
          <b>03</b>
          <span>리뷰 통계</span>
          <p>리뷰한 PR과 지적 유형을 한눈에 확인합니다.</p>
        </div>
      </section>
      <footer className="landing-footer">CO-DAY · 더 나은 코드를 만드는 하루</footer>
    </main>
  )
}

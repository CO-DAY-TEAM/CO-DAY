import { useEffect, useState } from 'react'
import { api, ApiError } from './api'
import type {
  Installation,
  RepoData,
  Repository,
  Review,
  ReviewData,
  Settings,
  User,
} from './api'
import './App.css'

const statuses: Record<string, string> = {
  queued: '대기',
  running: '진행 중',
  completed: '완료',
  failed: '실패',
  cancelled: '취소',
  superseded: '중단',
}
const categories: Record<string, string> = {
  bug: '버그',
  security: '보안',
  style: '스타일',
  maintainability: '유지보수성',
}
const date = (value: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))

function Brand() {
  return (
    <span className="brand">
      <span className="brand-icon" aria-hidden="true">
        co
      </span>
      CO-DAY<span className="brand-dot">.</span>
    </span>
  )
}

function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  disabled?: boolean
}) {
  return (
    <label className={`toggle-label ${disabled ? 'disabled' : ''}`}>
      <span>{label}</span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span className="toggle-track" aria-hidden="true" />
    </label>
  )
}

function SettingsForm({
  installation,
  repository,
  csrf,
  onSaved,
}: {
  installation: Installation
  repository?: Repository
  csrf: string
  onSaved: () => Promise<void>
}) {
  const [settings, setSettings] = useState<Settings>(
    repository?.settings ?? installation.settings,
  )
  const [paused, setPaused] = useState(installation.paused)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const canManage = repository
    ? repository.permission === 'admin'
    : installation.can_manage
  const disabled = !canManage || !!repository?.use_common || busy

  async function save() {
    setBusy(true)
    setMessage('')
    try {
      const path = repository
        ? `/settings/repositories/${repository.id}`
        : `/settings/installations/${installation.id}`
      await api(
        path,
        {
          method: 'PUT',
          body: JSON.stringify(
            repository ? { use_common: false, settings } : { settings, paused },
          ),
        },
        csrf,
      )
      await onSaved()
      setMessage('설정을 저장했습니다.')
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function changeCommon(value: boolean) {
    if (!repository) return
    if (
      value &&
      !window.confirm(
        '저장소의 독립 설정을 버리고 공통 설정을 적용합니다. 계속할까요?',
      )
    )
      return
    setBusy(true)
    setMessage('')
    try {
      await api(
        `/settings/repositories/${repository.id}`,
        { method: 'PUT', body: JSON.stringify({ use_common: value }) },
        csrf,
      )
      await onSaved()
    } catch (error) {
      setMessage((error as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel settings-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            {repository ? '저장소 설정' : '공통 설정'}
          </span>
          <h2>{repository?.full_name ?? installation.login}</h2>
        </div>
        <span className="tag">
          {repository
            ? '저장소'
            : installation.account_type === 'User'
              ? '개인 계정'
              : '조직'}
        </span>
      </div>
      {!canManage && (
        <p className="notice">
          변경은{' '}
          {repository ? '저장소 Admin' : '개인 계정 소유자 또는 조직 Owner'}에게
          요청해 주세요.
        </p>
      )}
      {repository && (
        <div className="setting-row">
          <Toggle
            label="공통 설정 사용"
            checked={repository.use_common}
            onChange={changeCommon}
            disabled={!canManage || busy}
          />
          <p>
            {repository.use_common
              ? `${installation.login}의 공통 설정과 이후 변경을 따릅니다.`
              : '이 저장소의 설정을 독립적으로 관리합니다.'}
          </p>
        </div>
      )}
      <div className="setting-row">
        <Toggle
          label="자동 리뷰"
          checked={settings.automatic}
          onChange={(automatic) => setSettings({ ...settings, automatic })}
          disabled={disabled}
        />
        <p>
          끄면 새 자동 리뷰와 대기 중인 자동 리뷰가 중지됩니다. 진행 중인 리뷰는
          완료하며, 수동 리뷰와 재시도는 가능합니다.
        </p>
      </div>
      <label className="field">
        <span>
          추가 리뷰 지침 <small>선택</small>
        </span>
        <p>
          비워 두면 기본 기준을 사용합니다. 팀의 규칙이나 중점적으로 확인할
          내용을 적어 주세요.
        </p>
        <textarea
          value={settings.instructions}
          maxLength={12000}
          rows={6}
          placeholder="예: 공개 API를 변경할 때 하위 호환성을 확인해 주세요."
          disabled={disabled}
          onChange={(e) =>
            setSettings({ ...settings, instructions: e.target.value })
          }
        />
      </label>
      <label className="field">
        <span>제외 경로</span>
        <p>분석에서 제외할 glob 패턴을 한 줄에 하나씩 입력해 주세요.</p>
        <textarea
          className="code-input"
          rows={5}
          value={settings.exclude_patterns.join('\n')}
          disabled={disabled}
          onChange={(e) =>
            setSettings({
              ...settings,
              exclude_patterns: e.target.value.split('\n'),
            })
          }
        />
      </label>
      {!repository && (
        <div className="setting-row pause-row">
          <Toggle
            label="이 계정의 전체 리뷰 중지"
            checked={paused}
            onChange={setPaused}
            disabled={!canManage || busy}
          />
          <p>
            모든 저장소의 새 자동·수동 리뷰와 재시도를 막고 대기 작업을
            취소합니다. 이미 진행 중인 작업은 완료합니다.
          </p>
        </div>
      )}
      <div className="form-footer">
        <span role="status">{message}</span>
        <button className="primary" disabled={disabled} onClick={save}>
          {busy ? '저장 중…' : '설정 저장'}
        </button>
      </div>
    </section>
  )
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [repos, setRepos] = useState<RepoData>({
    repositories: [],
    installations: [],
  })
  const [view, setView] = useState<'reviews' | 'settings'>('reviews')
  const [selected, setSelected] = useState('all')
  const [settingTarget, setSettingTarget] = useState('')
  const [data, setData] = useState<ReviewData | null>(null)
  const [focusedReview, setFocusedReview] = useState<Review | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [retrying, setRetrying] = useState('')

  useEffect(() => {
    api<User>('/auth/me')
      .then(setUser)
      .catch((error) => {
        if (!(error instanceof ApiError && error.status === 401))
          setError(error.message)
      })
      .finally(() => setAuthLoading(false))
  }, [])

  async function loadRepos() {
    const result = await api<RepoData>('/repos')
    setRepos(result)
    setSettingTarget(
      (previous) =>
        previous ||
        (result.installations[0] ? `i:${result.installations[0].id}` : ''),
    )
  }

  useEffect(() => {
    if (!user) return
    api<RepoData>('/repos')
      .then((result) => {
        setRepos(result)
        setSettingTarget(
          (previous) =>
            previous ||
            (result.installations[0] ? `i:${result.installations[0].id}` : ''),
        )
      })
      .catch((error) => setError(error.message))
    const id = new URLSearchParams(window.location.search).get('review')
    if (id)
      api<Review>(`/reviews/${encodeURIComponent(id)}`)
        .then((review) => {
          setFocusedReview(review)
          setSelected(String(review.repository_id))
        })
        .catch((error) => setError(error.message))
  }, [user])

  useEffect(() => {
    if (!user) return
    const abort = new AbortController()
    const query = new URLSearchParams({ page: String(page) })
    if (selected !== 'all') query.set('repository_id', selected)
    api<ReviewData>(`/reviews?${query}`, { signal: abort.signal })
      .then(setData)
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setData(null)
          setError(error.message)
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false)
      })
    return () => abort.abort()
  }, [user, selected, page, revision])

  async function retry(review: Review) {
    if (!user) return
    setRetrying(review.id)
    setError('')
    setNotice('')
    try {
      await api(`/reviews/${review.id}/retry`, { method: 'POST' }, user.csrf)
      setNotice('저장된 결과를 활용해 이어서 처리합니다.')
      if (focusedReview?.id === review.id)
        setFocusedReview({ ...focusedReview, status: 'queued', error: null })
      setLoading(true)
      setRevision((value) => value + 1)
    } catch (error) {
      setError((error as Error).message)
    } finally {
      setRetrying('')
    }
  }

  async function logout() {
    if (!user) return
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: { 'X-CSRF-Token': user.csrf },
    })
    window.location.assign('/')
  }

  if (authLoading)
    return (
      <main className="loading-screen">
        <Brand />
        <p>로그인을 확인하고 있습니다…</p>
      </main>
    )
  if (!user)
    return (
      <main className="landing">
        <header>
          <Brand />
          <span className="tag">AI 코드 리뷰</span>
        </header>
        <section className="landing-content">
          <span className="eyebrow">코드를 함께 읽는 또 하나의 동료</span>
          <h1>
            리뷰는 GitHub에서.
            <br />
            <span>팀의 기준은 여기서.</span>
          </h1>
          <p>
            PR의 변경 사항을 살펴보고, 근거 있는 리뷰와
            <br /> 바로 적용할 수 있는 수정 제안을 전합니다.
          </p>
          <a
            className="primary login-button"
            href={`/api/auth/login?return_to=${encodeURIComponent('/' + window.location.search)}`}
          >
            GitHub로 시작하기 ↗
          </a>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="landing-features">
            <span>
              01 <strong>PR 자동 리뷰</strong>
            </span>
            <span>
              02 <strong>팀별 리뷰 설정</strong>
            </span>
            <span>
              03 <strong>리뷰 통계</strong>
            </span>
          </div>
        </section>
        <footer>CO-DAY · 더 나은 코드를 만드는 하루</footer>
      </main>
    )

  const targetId = Number(settingTarget.split(':')[1])
  const targetRepo = settingTarget.startsWith('r:')
    ? repos.repositories.find((repo) => repo.id === targetId)
    : undefined
  const targetInstall = repos.installations.find(
    (install) => install.id === (targetRepo?.installation_id ?? targetId),
  )
  const displayed = data?.reviews ?? []
  const focusedCanRetry = repos.repositories.some(
    (repo) =>
      repo.id === focusedReview?.repository_id &&
      ['write', 'maintain', 'admin'].includes(repo.permission),
  )

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="/" className="brand-link">
          <Brand />
        </a>
        <span className="sidebar-label">대시보드</span>
        <nav aria-label="주 메뉴">
          <button
            className={view === 'reviews' ? 'active' : ''}
            onClick={() => setView('reviews')}
          >
            ▦　리뷰와 통계
          </button>
          <button
            className={view === 'settings' ? 'active' : ''}
            onClick={() => setView('settings')}
          >
            ⚙　리뷰 설정
          </button>
        </nav>
        <div className="sidebar-bottom">
          <a href={user.install_url} target="_blank" rel="noreferrer">
            저장소 연결 관리 ↗
          </a>
          <div className="user">
            <span className="avatar">
              {user.login.slice(0, 1).toUpperCase()}
            </span>
            <span>{user.login}</span>
            <button onClick={logout} aria-label="로그아웃" title="로그아웃">
              ↪
            </button>
          </div>
        </div>
      </aside>
      <main className="workspace">
        <header className="page-header">
          <div>
            <span className="eyebrow">
              CO-DAY / {view === 'reviews' ? '리뷰와 통계' : '리뷰 설정'}
            </span>
            <h1>{view === 'reviews' ? '리뷰와 통계' : '리뷰 설정'}</h1>
            <p>
              {view === 'reviews'
                ? '리뷰의 흐름을 확인하고, 코드 이야기는 GitHub에서 이어가세요.'
                : '팀의 공통 기준과 저장소별 리뷰 방식을 관리하세요.'}
            </p>
          </div>
          <button
            className="secondary"
            disabled={loading}
            onClick={() => {
              setLoading(true)
              setError('')
              setRevision((value) => value + 1)
              loadRepos().catch((error) => setError(error.message))
            }}
          >
            ↻ 새로고침
          </button>
        </header>
        {error && (
          <div role="alert" className="banner error">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="banner success">
            {notice}
          </div>
        )}
        {view === 'reviews' ? (
          <>
            <div className="toolbar">
              <label htmlFor="repository-filter">저장소</label>
              <select
                id="repository-filter"
                value={selected}
                onChange={(e) => {
                  setLoading(true)
                  setError('')
                  setSelected(e.target.value)
                  setPage(1)
                  setFocusedReview(null)
                }}
              >
                <option value="all">접근 가능한 모든 저장소</option>
                {repos.repositories.map((repo) => (
                  <option key={repo.id} value={repo.id}>
                    {repo.full_name}
                  </option>
                ))}
              </select>
              <span className="muted">누적 기록</span>
            </div>
            <section className="stats-grid" aria-label="리뷰 통계">
              <div className="stat-card">
                <span className="eyebrow">리뷰한 PR</span>
                <div className="stat-number">
                  {data?.stats.reviewed_prs.toLocaleString() ?? '—'}
                  <small>개</small>
                </div>
                <p>같은 PR의 재시도는 한 번으로 집계</p>
              </div>
              <div className="stat-card">
                <span className="eyebrow">게시한 지적</span>
                <div className="stat-number">
                  {data?.stats.findings.toLocaleString() ?? '—'}
                  <small>개</small>
                </div>
                <p>GitHub에 게시한 지적만 집계</p>
              </div>
              <div className="stat-card distribution">
                <span className="eyebrow">지적 유형</span>
                {Object.entries(categories).map(([key, label]) => (
                  <div className="distribution-row" key={key}>
                    <span>{label}</span>
                    <div className="bar-track">
                      <div
                        className={`bar ${key}`}
                        style={{
                          width: `${data?.stats.findings ? ((data.stats.categories[key] ?? 0) / data.stats.findings) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <strong>{data?.stats.categories[key] ?? 0}</strong>
                  </div>
                ))}
              </div>
            </section>
            {focusedReview &&
              !displayed.some((review) => review.id === focusedReview.id) && (
                <section className="panel focused">
                  <h2>선택한 리뷰 · #{focusedReview.pr_number}</h2>
                  <p>
                    {focusedReview.title} · {statuses[focusedReview.status]}
                  </p>
                  {focusedReview.error && <p>{focusedReview.error}</p>}
                  <div className="actions">
                    <a
                      href={focusedReview.github_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      GitHub PR ↗
                    </a>
                    {focusedReview.status === 'failed' &&
                      focusedReview.can_resume &&
                      focusedCanRetry && (
                        <button
                          onClick={() => retry(focusedReview)}
                          disabled={!!retrying}
                        >
                          재시도
                        </button>
                      )}
                  </div>
                </section>
              )}
            <section className="panel review-panel">
              <div className="panel-heading">
                <div>
                  <h2>리뷰 목록</h2>
                  <p>진행 상태와 리뷰 결과는 PR에서도 확인할 수 있습니다.</p>
                </div>
                <span className="tag">
                  {loading ? '불러오는 중…' : 'GitHub PR'}
                </span>
              </div>
              {displayed.length ? (
                <div className="review-list">
                  {displayed.map((review) => (
                    <article
                      key={review.id}
                      className={`review-row ${focusedReview?.id === review.id ? 'highlight' : ''}`}
                    >
                      <div className="pr-symbol" aria-hidden="true">
                        ⑂
                      </div>
                      <div className="review-main">
                        <div className="review-title">
                          <a
                            href={review.github_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {review.title}
                          </a>
                          <span className={`status ${review.status}`}>
                            {statuses[review.status]}
                          </span>
                        </div>
                        <p className="review-meta">
                          {review.repository} <span>#{review.pr_number}</span>{' '}
                          <code>{review.head_sha.slice(0, 7)}</code> ·{' '}
                          {date(review.created_at)}
                        </p>
                        {review.error && (
                          <p className="review-error">{review.error}</p>
                        )}
                      </div>
                      <div className="review-actions">
                        {review.status === 'failed' && review.can_retry && (
                          <button
                            className="secondary"
                            onClick={() => retry(review)}
                            disabled={!!retrying}
                          >
                            {retrying === review.id ? '요청 중…' : '재시도'}
                          </button>
                        )}
                        <a
                          className="external-link"
                          href={review.github_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`${review.title} GitHub에서 보기`}
                        >
                          ↗
                        </a>
                      </div>
                    </article>
                  ))}
                </div>
              ) : (
                <div className="empty-state">
                  <span aria-hidden="true">⑂</span>
                  <h3>
                    {loading
                      ? '리뷰를 불러오고 있습니다'
                      : '아직 리뷰가 없습니다'}
                  </h3>
                  <p>
                    저장소를 연결한 뒤 PR을 생성하거나, PR 댓글로 리뷰를 요청하세요.
                  </p>
                  <code>{user.review_command}</code>
                </div>
              )}
              <div className="pagination">
                <button
                  disabled={page === 1 || loading}
                  onClick={() => {
                    setLoading(true)
                    setPage(page - 1)
                  }}
                >
                  이전
                </button>
                <span>{page} 페이지</span>
                <button
                  disabled={!data?.has_more || loading}
                  onClick={() => {
                    setLoading(true)
                    setPage(page + 1)
                  }}
                >
                  다음
                </button>
              </div>
            </section>
            <div className="hint">
              <span>안내</span> 수동 리뷰는 PR 댓글에{' '}
              <code>{user.review_command}</code>를 입력하세요. 저장소 Write 이상
              권한이 필요합니다.
            </div>
          </>
        ) : (
          <>
            <div className="toolbar">
              <label htmlFor="settings-target">설정 대상</label>
              <select
                id="settings-target"
                value={settingTarget}
                onChange={(e) => setSettingTarget(e.target.value)}
              >
                {repos.installations.map((install) => (
                  <option value={`i:${install.id}`} key={`i:${install.id}`}>
                    {install.login} · 공통 설정
                  </option>
                ))}
                {repos.repositories.map((repo) => (
                  <option value={`r:${repo.id}`} key={`r:${repo.id}`}>
                    {repo.full_name} · 저장소 설정
                  </option>
                ))}
              </select>
            </div>
            {targetInstall ? (
              <SettingsForm
                key={`${settingTarget}:${JSON.stringify(targetRepo ?? targetInstall)}`}
                installation={targetInstall}
                repository={targetRepo}
                csrf={user.csrf}
                onSaved={loadRepos}
              />
            ) : (
              <section className="panel empty-state">
                <h2>먼저 저장소를 연결해 주세요</h2>
                <p>
                  설치한 계정의 공통 설정과 저장소 설정이 여기에 표시됩니다.
                </p>
                <a
                  className="primary"
                  href={user.install_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  GitHub App 설치 ↗
                </a>
              </section>
            )}
          </>
        )}
        <footer className="workspace-footer">
          CO-DAY <span>리뷰는 더 선명하게, 협업은 더 가볍게.</span>
        </footer>
      </main>
    </div>
  )
}

export default App

import { useEffect, useRef, useState } from 'react'
import { api, ApiError } from './api/client'
import type { Review, User } from './api/types'
import { Banner } from './components/Banner'
import { StatusBar } from './components/layout/StatusBar'
import { Titlebar } from './components/layout/Titlebar'
import { HelpModal } from './components/modals/HelpModal'
import { useRepos } from './hooks/useRepos'
import { useReviews } from './hooks/useReviews'
import { useShortcuts } from './hooks/useShortcuts'
import { useTheme } from './hooks/useTheme'
import { views } from './lib/constants'
import type { View } from './lib/constants'
import { AuthLoading } from './pages/landing/AuthLoading'
import { LandingPage } from './pages/landing/LandingPage'
import { ReposPage } from './pages/repos/ReposPage'
import { ReviewsPage } from './pages/reviews/ReviewsPage'
import { SettingsPage } from './pages/settings/SettingsPage'
import './App.css'

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [view, setView] = useState<View>('reviews')
  const [theme, setTheme] = useTheme()
  const [helpOpen, setHelpOpen] = useState(false)
  const [selected, setSelected] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [focusedReview, setFocusedReview] = useState<Review | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [retrying, setRetrying] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const { repos, settingTarget, setSettingTarget, loadRepos } = useRepos(
    user,
    setError,
  )
  const { data, loading, setLoading, syncedAt } = useReviews(
    user,
    selected,
    page,
    revision,
    setError,
  )

  useEffect(() => {
    api<User>('/auth/me')
      .then(setUser)
      .catch((error) => {
        if (!(error instanceof ApiError && error.status === 401))
          setError(error.message)
      })
      .finally(() => setAuthLoading(false))
  }, [])

  // 알림 링크(?review=<id>)로 들어오면 그 리뷰를 위에 띄운다
  useEffect(() => {
    if (!user) return
    const id = new URLSearchParams(window.location.search).get('review')
    if (id)
      api<Review>(`/reviews/${encodeURIComponent(id)}`)
        .then((review) => {
          setFocusedReview(review)
          setSelected(String(review.repository_id))
        })
        .catch((error) => setError(error.message))
  }, [user])

  function refresh() {
    setLoading(true)
    setError('')
    setRevision((value) => value + 1)
    loadRepos().catch((error) => setError(error.message))
  }

  useShortcuts(!!user, (event) => {
    if (event.key === '?') setHelpOpen(true)
    else if (event.key === '1') setView('reviews')
    else if (event.key === '2') setView('repos')
    else if (event.key === '3') setView('settings')
    else if (event.key.toLowerCase() === 'r' && !loading) refresh()
    else if (event.key === '/' && view === 'reviews') {
      event.preventDefault()
      searchRef.current?.focus()
    }
  })

  function changeRepository(value: string) {
    setLoading(true)
    setError('')
    setSelected(value)
    setPage(1)
    setFocusedReview(null)
  }

  function changePage(value: number) {
    setLoading(true)
    setPage(value)
  }

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

  if (authLoading) return <AuthLoading />
  if (!user) return <LandingPage error={error} />

  const current = views.find((item) => item.key === view)!
  const selectedRepo = repos.repositories.find(
    (repo) => String(repo.id) === selected,
  )
  const command =
    view === 'reviews'
      ? `co-day reviews --repo=${selectedRepo?.full_name ?? 'all'}`
      : `co-day ${current.command}`

  return (
    <div className="terminal">
      <Titlebar
        user={user}
        view={view}
        onViewChange={setView}
        theme={theme}
        onThemeChange={setTheme}
        onLogout={logout}
      />

      <main className="page">
        <header className="page-head">
          <div>
            <div className="breadcrumb">co-day / {current.title}</div>
            <h1 className="command">
              <span className="accent">$</span> {command}
            </h1>
            <p>{current.description}</p>
          </div>
          <button className="button" disabled={loading} onClick={refresh}>
            {loading ? '⠹ 동기화 중' : '↻ 새로고침'} <kbd>R</kbd>
          </button>
        </header>

        {error && (
          <Banner kind="error" message={error} onClose={() => setError('')} />
        )}
        {notice && (
          <Banner kind="ok" message={notice} onClose={() => setNotice('')} />
        )}

        {view === 'reviews' && (
          <ReviewsPage
            user={user}
            repositories={repos.repositories}
            selected={selected}
            onRepositoryChange={changeRepository}
            data={data}
            loading={loading}
            focusedReview={focusedReview}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            query={query}
            onQueryChange={setQuery}
            searchRef={searchRef}
            page={page}
            onPageChange={changePage}
            retrying={retrying}
            onRetry={retry}
          />
        )}
        {view === 'repos' && (
          <ReposPage
            user={user}
            repos={repos}
            onShowReviews={(id) => {
              changeRepository(String(id))
              setView('reviews')
            }}
            onOpenSettings={(id) => {
              setSettingTarget(`r:${id}`)
              setView('settings')
            }}
          />
        )}
        {view === 'settings' && (
          <SettingsPage
            user={user}
            repos={repos}
            target={settingTarget}
            onTargetChange={setSettingTarget}
            onSaved={loadRepos}
          />
        )}
      </main>

      <footer className="workspace-footer">
        CO-DAY — 리뷰는 더 선명하게, 협업은 더 가볍게.
      </footer>
      <StatusBar
        login={user.login}
        repoCount={repos.repositories.length}
        loading={loading}
        syncedAt={syncedAt}
        onHelp={() => setHelpOpen(true)}
      />
      {helpOpen && <HelpModal onClose={() => setHelpOpen(false)} />}
    </div>
  )
}

export default App

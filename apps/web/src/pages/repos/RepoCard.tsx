import type { Installation, Repository } from '../../api/types'
import { Panel } from '../../components/Panel'
import './RepoCard.css'

export function RepoCard({
  repo,
  installation,
  onShowReviews,
  onOpenSettings,
}: {
  repo: Repository
  installation?: Installation
  onShowReviews: () => void
  onOpenSettings: () => void
}) {
  const automatic = repo.use_common
    ? installation?.settings.automatic
    : repo.settings.automatic
  const name = repo.full_name.split('/').pop() ?? repo.full_name

  return (
    <Panel className="repo-card">
      <div className="repo-top">
        <span className="repo-initial" aria-hidden="true">
          {name.slice(0, 2).toUpperCase()}
        </span>
        <span className="repo-name">
          <strong>{name}</strong>
          <small>{repo.full_name}</small>
        </span>
        <span
          className={`switch ${automatic && !installation?.paused ? 'on' : ''}`}
          title="자동 리뷰"
        >
          {installation?.paused
            ? '[중지됨]'
            : automatic
              ? '[●  ON]'
              : '[OFF  ○]'}
        </span>
      </div>
      <div className="badges">
        <span>{repo.private ? 'private' : 'public'}</span>
        <span>{repo.permission}</span>
        <span>{repo.use_common ? '공통 설정' : '독립 설정'}</span>
      </div>
      <div className="repo-actions">
        <span className="muted">자동 리뷰</span>
        <span>
          <button className="button small" onClick={onShowReviews}>
            리뷰 보기
          </button>
          <button className="button small" onClick={onOpenSettings}>
            설정
          </button>
        </span>
      </div>
    </Panel>
  )
}

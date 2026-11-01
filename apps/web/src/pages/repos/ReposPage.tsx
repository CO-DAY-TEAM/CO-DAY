import type { RepoData, User } from '../../api/types'
import { EmptyState } from '../../components/EmptyState'
import { RepoCard } from './RepoCard'
import './ReposPage.css'

export function ReposPage({
  user,
  repos,
  onShowReviews,
  onOpenSettings,
}: {
  user: User
  repos: RepoData
  onShowReviews: (repositoryId: number) => void
  onOpenSettings: (repositoryId: number) => void
}) {
  return (
    <>
      <div className="toolbar">
        <b>{repos.repositories.length}개 연동됨</b>
        <a
          className="button primary toolbar-end"
          href={user.install_url}
          target="_blank"
          rel="noreferrer"
        >
          ＋ 저장소 연결 ↗
        </a>
      </div>
      {repos.repositories.length ? (
        <div className="repo-grid">
          {repos.repositories.map((repo) => (
            <RepoCard
              key={repo.id}
              repo={repo}
              installation={repos.installations.find(
                (item) => item.id === repo.installation_id,
              )}
              onShowReviews={() => onShowReviews(repo.id)}
              onOpenSettings={() => onOpenSettings(repo.id)}
            />
          ))}
          <a
            className="add-repo"
            href={user.install_url}
            target="_blank"
            rel="noreferrer"
          >
            ＋<span>저장소 연결 관리 ↗</span>
          </a>
        </div>
      ) : (
        <EmptyState boxed>
          <strong>먼저 저장소를 연결해 주세요</strong>
          <p>GitHub App을 설치하면 연결한 저장소가 여기에 표시됩니다.</p>
          <a
            className="button primary"
            href={user.install_url}
            target="_blank"
            rel="noreferrer"
          >
            GitHub App 설치 ↗
          </a>
        </EmptyState>
      )}
    </>
  )
}

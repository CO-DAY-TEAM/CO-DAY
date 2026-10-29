import type { RepoData, User } from '../../api/types'
import { EmptyState } from '../../components/EmptyState'
import { SettingsForm } from './SettingsForm'
import './SettingsPage.css'

export function SettingsPage({
  user,
  repos,
  target,
  onTargetChange,
  onSaved,
}: {
  user: User
  repos: RepoData
  target: string
  onTargetChange: (value: string) => void
  onSaved: () => Promise<void>
}) {
  // target은 'i:<설치 id>'(공통 설정) 또는 'r:<저장소 id>'(저장소 설정)
  const targetId = Number(target.split(':')[1])
  const targetRepo = target.startsWith('r:')
    ? repos.repositories.find((repo) => repo.id === targetId)
    : undefined
  const targetInstall = repos.installations.find(
    (install) => install.id === (targetRepo?.installation_id ?? targetId),
  )

  return (
    <div className="settings">
      <div className="toolbar">
        <label htmlFor="settings-target">설정 대상</label>
        <select
          id="settings-target"
          value={target}
          onChange={(e) => onTargetChange(e.target.value)}
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
          key={`${target}:${JSON.stringify(targetRepo ?? targetInstall)}`}
          installation={targetInstall}
          repository={targetRepo}
          csrf={user.csrf}
          onSaved={onSaved}
        />
      ) : (
        <EmptyState boxed>
          <strong>먼저 저장소를 연결해 주세요</strong>
          <p>설치한 계정의 공통 설정과 저장소 설정이 여기에 표시됩니다.</p>
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
    </div>
  )
}

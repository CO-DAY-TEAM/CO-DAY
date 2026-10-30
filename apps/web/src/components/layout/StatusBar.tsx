import { clock } from '../../lib/format'
import './StatusBar.css'

export function StatusBar({
  login,
  repoCount,
  loading,
  syncedAt,
  onHelp,
}: {
  login: string
  repoCount: number
  loading: boolean
  syncedAt: Date | null
  onHelp: () => void
}) {
  return (
    <div className="statusbar">
      <b>NORMAL</b>
      <span>{login}</span>
      <span>{repoCount} repos</span>
      <span>
        {loading
          ? 'syncing…'
          : syncedAt
            ? `last sync ${clock(syncedAt)}`
            : 'not synced'}
      </span>
      <button onClick={onHelp}>? 단축키</button>
      <em>/ 검색　r 새로고침</em>
    </div>
  )
}

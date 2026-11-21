import { views } from '../../lib/constants'
import type { View } from '../../lib/constants'
import { clock } from '../../lib/format'
import './StatusBar.css'

// 경로 끝을 가장 긴 화면 이름 길이로 채워, 화면을 바꿔도 가운데 정렬한 경로가 움직이지 않게 한다
const viewLength = Math.max(...views.map((item) => item.key.length))

export function StatusBar({
  login,
  view,
  repoCount,
  loading,
  syncedAt,
  onHelp,
}: {
  login: string
  view: View
  repoCount: number
  loading: boolean
  syncedAt: Date | null
  onHelp: () => void
}) {
  return (
    <div className="statusbar">
      <b>NORMAL</b>
      <span>{repoCount} repos</span>
      <span>
        {loading
          ? 'syncing…'
          : syncedAt
            ? `last sync ${clock(syncedAt)}`
            : 'not synced'}
      </span>
      <span className="statusbar-path">
        {login}@co-day: ~/{view.padEnd(viewLength)}
      </span>
      <button onClick={onHelp}>? 단축키</button>
      <em>/ 검색　r 새로고침</em>
    </div>
  )
}

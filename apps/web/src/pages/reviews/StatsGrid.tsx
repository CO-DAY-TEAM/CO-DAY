import type { ReviewData } from '../../api/types'
import { Panel } from '../../components/Panel'
import { categories } from '../../lib/constants'
import './StatsGrid.css'

export function StatsGrid({ stats }: { stats?: ReviewData['stats'] }) {
  return (
    <section className="stats-grid" aria-label="리뷰 통계">
      <Panel title="리뷰한 PR" className="stat">
        <strong>
          {stats?.reviewed_prs.toLocaleString() ?? '—'}
          <small>개</small>
        </strong>
        <small>같은 PR의 재시도는 한 번으로 집계</small>
      </Panel>
      <Panel title="게시한 지적" className="stat">
        <strong>
          {stats?.findings.toLocaleString() ?? '—'}
          <small>개</small>
        </strong>
        <small>GitHub에 게시한 지적만 집계</small>
      </Panel>
      <Panel title="지적 유형" className="stat">
        {Object.entries(categories).map(([key, label]) => {
          const count = stats?.categories[key] ?? 0
          const total = stats?.findings ?? 0
          return (
            <div className={`dist dist-${key}`} key={key}>
              <span>{label}</span>
              <div className="bar" aria-hidden="true">
                <i style={{ width: `${total ? (count / total) * 100 : 0}%` }} />
              </div>
              <b>{count}</b>
            </div>
          )
        })}
      </Panel>
    </section>
  )
}

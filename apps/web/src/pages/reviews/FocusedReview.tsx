import type { Review } from '../../api/types'
import { Panel } from '../../components/Panel'
import { StatusTag } from '../../components/StatusTag'
import { date } from '../../lib/format'
import './FocusedReview.css'

// URL의 ?review=<id>로 들어온 리뷰가 현재 페이지 목록에 없을 때 위에 따로 보여준다
export function FocusedReview({
  review,
  canRetry,
  retrying,
  onRetry,
}: {
  review: Review
  canRetry: boolean
  retrying: string
  onRetry: (review: Review) => void
}) {
  return (
    <Panel title={`선택한 리뷰 · #${review.pr_number}`} className="focused">
      <div className="focused-head">
        <b>{review.title}</b>
        <StatusTag status={review.status} />
      </div>
      <p className="muted">
        {review.repository} ·{' '}
        <code className="sha">{review.head_sha.slice(0, 7)}</code> ·{' '}
        {date(review.created_at)}
      </p>
      {review.error && <p className="row-error">{review.error}</p>}
      <div className="focused-actions">
        <a
          className="button"
          href={review.github_url}
          target="_blank"
          rel="noreferrer"
        >
          GitHub PR ↗
        </a>
        {review.status === 'failed' && review.can_resume && canRetry && (
          <button
            className="button"
            onClick={() => onRetry(review)}
            disabled={!!retrying}
          >
            {retrying === review.id ? '⠋ 요청 중…' : '재시도'}
          </button>
        )}
      </div>
    </Panel>
  )
}

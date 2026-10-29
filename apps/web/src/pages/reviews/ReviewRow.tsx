import type { Review } from '../../api/types'
import { StatusTag } from '../../components/StatusTag'
import { ago, date } from '../../lib/format'
import './ReviewRow.css'

export function ReviewTableHead() {
  return (
    <div className="table-head">
      <span>PR</span>
      <span>레포</span>
      <span>상태</span>
      <span>시각</span>
    </div>
  )
}

export function ReviewRow({
  review,
  highlight,
  retrying,
  onRetry,
}: {
  review: Review
  highlight: boolean
  retrying: string
  onRetry: (review: Review) => void
}) {
  return (
    <article
      className={`review-row ${highlight ? 'highlight' : ''} ${review.status === 'failed' ? 'failed' : ''}`}
    >
      <div className="pr-cell">
        <span className="pr-symbol" aria-hidden="true">
          ⑂
        </span>
        <span className="pr-text">
          <a href={review.github_url} target="_blank" rel="noreferrer">
            {review.title}
          </a>
          <small>
            #{review.pr_number}{' '}
            <code className="sha">{review.head_sha.slice(0, 7)}</code>
            {review.attempt > 1 && ` · 시도 ${review.attempt}`}
          </small>
          {review.error && <em className="row-error">{review.error}</em>}
        </span>
      </div>
      <code className="repo-cell">{review.repository}</code>
      <StatusTag status={review.status} />
      <span className="row-end">
        <span className="muted" title={date(review.created_at)}>
          {ago(review.created_at)}
        </span>
        {review.status === 'failed' && review.can_retry && (
          <button
            className="button small"
            onClick={() => onRetry(review)}
            disabled={!!retrying}
          >
            {retrying === review.id ? '⠋ 요청 중…' : '재시도'}
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
      </span>
    </article>
  )
}

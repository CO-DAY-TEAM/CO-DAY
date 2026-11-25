import type { RefObject } from 'react'
import type { Repository, Review, ReviewData, User } from '../../api/types'
import { EmptyState } from '../../components/EmptyState'
import { Panel } from '../../components/Panel'
import { statuses, statusFilters } from '../../lib/constants'
import { FocusedReview } from './FocusedReview'
import { ReviewRow, ReviewTableHead } from './ReviewRow'
import { StatsGrid } from './StatsGrid'
import './ReviewsPage.css'

export function ReviewsPage({
  user,
  repositories,
  selected,
  onRepositoryChange,
  data,
  loading,
  focusedReview,
  statusFilter,
  onStatusFilterChange,
  query,
  onQueryChange,
  searchRef,
  page,
  onPageChange,
  lastPage,
  displayed,
  filtering,
  retrying,
  onRetry,
}: {
  user: User
  repositories: Repository[]
  selected: string
  onRepositoryChange: (value: string) => void
  data: ReviewData | null
  loading: boolean
  focusedReview: Review | null
  statusFilter: string
  onStatusFilterChange: (value: string) => void
  query: string
  onQueryChange: (value: string) => void
  searchRef: RefObject<HTMLInputElement | null>
  page: number
  onPageChange: (page: number) => void
  lastPage: number
  displayed: Review[]
  filtering: boolean
  retrying: string
  onRetry: (review: Review) => void
}) {
  const focusedCanRetry = repositories.some(
    (repo) =>
      repo.id === focusedReview?.repository_id &&
      ['write', 'maintain', 'admin'].includes(repo.permission),
  )

  return (
    <>
      <div className="toolbar">
        <label htmlFor="repository-filter">저장소</label>
        <select
          id="repository-filter"
          value={selected}
          onChange={(e) => onRepositoryChange(e.target.value)}
        >
          <option value="all">접근 가능한 모든 저장소</option>
          {repositories.map((repo) => (
            <option key={repo.id} value={repo.id}>
              {repo.full_name}
            </option>
          ))}
        </select>
      </div>

      <StatsGrid stats={data?.stats} />

      <div className="hint">
        <b>ℹ 안내</b> 수동 리뷰는 PR 댓글에 <code>{user.review_command}</code>를
        입력하세요. 저장소 Write 이상 권한이 필요합니다.
      </div>

      {focusedReview &&
        !displayed.some((review) => review.id === focusedReview.id) && (
          <FocusedReview
            review={focusedReview}
            canRetry={focusedCanRetry}
            retrying={retrying}
            onRetry={onRetry}
          />
        )}

      <div className="review-tools">
        <div className="filters" role="group" aria-label="상태 필터">
          {statusFilters.map((key) => (
            <button
              key={key}
              className={statusFilter === key ? 'selected' : ''}
              aria-pressed={statusFilter === key}
              onClick={() => onStatusFilterChange(key)}
            >
              {key === 'all' ? '전체' : statuses[key]}
            </button>
          ))}
        </div>
        <label className="search">
          <span aria-hidden="true">/</span>
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="PR 제목·저장소 검색…"
            aria-label="PR 검색"
          />
        </label>
      </div>

      <Panel className="review-panel">
        <ReviewTableHead />
        {displayed.length ? (
          <div className="review-list">
            {displayed.map((review) => (
              <ReviewRow
                key={review.id}
                review={review}
                highlight={focusedReview?.id === review.id}
                retrying={retrying}
                onRetry={onRetry}
              />
            ))}
          </div>
        ) : loading ? (
          <div className="skeleton" aria-label="불러오는 중">
            <p>░░░░░░░░░░░░░░░░░░░░░░░░░░░░</p>
            <p>░░░░░░░░░░░░░░░░░░░░</p>
            <p>░░░░░░░░░░░░░░░░░░░░░░░░</p>
          </div>
        ) : filtering && data?.reviews.length ? (
          <EmptyState>
            <strong>조건에 맞는 리뷰가 없습니다</strong>
            <button
              className="button"
              onClick={() => {
                onStatusFilterChange('all')
                onQueryChange('')
              }}
            >
              필터 초기화
            </button>
          </EmptyState>
        ) : (
          <EmptyState>
            <b aria-hidden="true">⑂</b>
            <strong>아직 리뷰가 없습니다</strong>
            <p>
              저장소를 연결한 뒤 PR을 생성하거나, PR 댓글로 리뷰를 요청하세요.
            </p>
            <code className="command-chip">{user.review_command}</code>
          </EmptyState>
        )}
      </Panel>

      <div className="pagination">
        <button
          className="button"
          disabled={page === 1 || loading}
          onClick={() => onPageChange(page - 1)}
        >
          ← 이전
        </button>
        <span>{page} 페이지</span>
        <button
          className="button"
          disabled={page === lastPage || loading}
          onClick={() => onPageChange(page + 1)}
        >
          다음 →
        </button>
      </div>
    </>
  )
}

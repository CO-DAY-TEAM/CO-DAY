import { useState } from 'react'
import type { Review } from '../api/types'

const pageSize = 10

// 리뷰 목록의 상태 필터, 검색어, 페이지를 한곳에서 관리한다.
// 필터링한 결과로 마지막 페이지를 계산하고, 보여줄 페이지만 잘라 돌려준다.
export function useReviewList(reviews: Review[] = []) {
  const [statusFilter, setStatusFilter] = useState('all')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)

  const filtered = reviews.filter(
    (review) =>
      (statusFilter === 'all' || review.status === statusFilter) &&
      `${review.title} ${review.repository} #${review.pr_number}`
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  )
  const lastPage = Math.max(1, Math.ceil(filtered.length / pageSize))
  // 새로고침 뒤 목록이 줄어 보던 페이지가 없어지면 마지막 페이지로 옮긴다
  // 렌더링 중에 바로 고치므로 범위를 벗어난 page는 화면에 그려지지 않는다
  if (page > lastPage) setPage(lastPage)
  const displayed = filtered.slice((page - 1) * pageSize, page * pageSize)
  const filtering = statusFilter !== 'all' || query.trim() !== ''

  function changeStatusFilter(value: string) {
    setStatusFilter(value)
    setPage(1)
  }

  function changeQuery(value: string) {
    setQuery(value)
    setPage(1)
  }

  return {
    statusFilter,
    changeStatusFilter,
    query,
    changeQuery,
    page,
    setPage,
    lastPage,
    displayed,
    filtering,
  }
}

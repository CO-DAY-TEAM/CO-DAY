import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { ReviewData, User } from '../api/types'

// selected/page/revision이 바뀌면 리뷰 목록을 다시 불러온다.
// loading을 true로 켜는 건 호출하는 쪽 책임이다.
// onError는 setState처럼 바뀌지 않는 함수를 넘겨야 한다(바뀌면 다시 불러온다).
export function useReviews(
  user: User | null,
  selected: string,
  page: number,
  revision: number,
  onError: (message: string) => void,
) {
  const [data, setData] = useState<ReviewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncedAt, setSyncedAt] = useState<Date | null>(null)

  useEffect(() => {
    if (!user) return
    const abort = new AbortController()
    const query = new URLSearchParams({ page: String(page) })
    if (selected !== 'all') query.set('repository_id', selected)
    api<ReviewData>(`/reviews?${query}`, { signal: abort.signal })
      .then((result) => {
        setData(result)
        setSyncedAt(new Date())
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setData(null)
          onError(error.message)
        }
      })
      .finally(() => {
        if (!abort.signal.aborted) setLoading(false)
      })
    return () => abort.abort()
  }, [user, selected, page, revision, onError])

  return { data, loading, setLoading, syncedAt }
}

import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RepoData, User } from '../api/types'

// 저장소 목록과, 설정 화면에서 고른 대상('i:<설치 id>' 또는 'r:<저장소 id>')
export function useRepos(user: User | null, onError: (message: string) => void) {
  const [repos, setRepos] = useState<RepoData>({
    repositories: [],
    installations: [],
  })
  const [settingTarget, setSettingTarget] = useState('')

  function apply(result: RepoData) {
    setRepos(result)
    setSettingTarget(
      (previous) =>
        previous ||
        (result.installations[0] ? `i:${result.installations[0].id}` : ''),
    )
  }

  async function loadRepos() {
    apply(await api<RepoData>('/repos'))
  }

  useEffect(() => {
    if (!user) return
    api<RepoData>('/repos')
      .then(apply)
      .catch((error) => onError(error.message))
  }, [user, onError])

  return { repos, settingTarget, setSettingTarget, loadRepos }
}

export type Settings = {
  automatic: boolean
  instructions: string
  exclude_patterns: string[]
}
export type Installation = {
  id: number
  login: string
  account_type: string
  paused: boolean
  settings: Settings
  can_manage: boolean
}
export type Repository = {
  id: number
  full_name: string
  private: boolean
  installation_id: number
  permission: string
  use_common: boolean
  settings: Settings
}
export type User = {
  id: number
  login: string
  csrf: string
  install_url: string
  review_command: string
}
export type Review = {
  id: string
  repository_id: number
  repository: string
  pr_number: number
  title: string
  head_sha: string
  status: string
  error: string | null
  created_at: string
  attempt: number
  github_url: string
  can_retry: boolean
  can_resume: boolean
}
export type RepoData = {
  installations: Installation[]
  repositories: Repository[]
}
export type ReviewData = {
  reviews: Review[]
  has_more: boolean
  stats: {
    reviewed_prs: number
    findings: number
    categories: Record<string, number>
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  csrf?: string,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      ...options.headers,
    },
  })
  const body = await response.json().catch(() => null)
  if (!response.ok)
    throw new ApiError(
      response.status,
      body?.message ??
        '요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.',
    )
  return body as T
}

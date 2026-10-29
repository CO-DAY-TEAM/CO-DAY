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

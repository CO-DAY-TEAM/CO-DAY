export type View = 'reviews' | 'repos' | 'settings'

export const statuses: Record<string, string> = {
  queued: '대기',
  running: '진행 중',
  completed: '완료',
  failed: '실패',
  cancelled: '취소',
  superseded: '중단',
}
export const statusFilters = ['all', 'running', 'completed', 'queued', 'failed']
export const categories: Record<string, string> = {
  bug: '버그',
  security: '보안',
  style: '스타일',
  maintainability: '유지보수성',
}
export const views: {
  key: View
  label: string
  title: string
  command: string
  description: string
}[] = [
  {
    key: 'reviews',
    label: '대시보드',
    title: '리뷰와 통계',
    command: 'reviews',
    description: '리뷰의 흐름을 확인하고, 코드 이야기는 GitHub에서 이어가세요.',
  },
  {
    key: 'repos',
    label: '레포지토리',
    title: '레포지토리',
    command: 'repos --list',
    description: 'CO-DAY가 리뷰하는 GitHub 저장소와 내 권한을 확인합니다.',
  },
  {
    key: 'settings',
    label: '설정',
    title: '리뷰 설정',
    command: 'config',
    description: '팀의 공통 기준과 저장소별 리뷰 방식을 관리하세요.',
  },
]

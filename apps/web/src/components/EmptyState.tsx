import type { ReactNode } from 'react'
import { Panel } from './Panel'
// Panel.css보다 뒤에 와야 .empty의 padding이 .panel을 덮는다
import './EmptyState.css'

export function EmptyState({
  boxed = false,
  children,
}: {
  boxed?: boolean
  children: ReactNode
}) {
  if (boxed) return <Panel className="empty">{children}</Panel>
  return <div className="empty">{children}</div>
}

import type { ReactNode } from 'react'
import './Panel.css'

export function Panel({
  title,
  className = '',
  children,
}: {
  title?: ReactNode
  className?: string
  children: ReactNode
}) {
  return (
    <section className={`panel ${className}`}>
      {title && <div className="panel-title">{title}</div>}
      {children}
    </section>
  )
}

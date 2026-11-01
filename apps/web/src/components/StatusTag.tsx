import { statuses } from '../lib/constants'
import './StatusTag.css'

export function StatusTag({ status }: { status: string }) {
  return (
    <span className={`status status-${status}`}>
      [{statuses[status] ?? status}]
    </span>
  )
}

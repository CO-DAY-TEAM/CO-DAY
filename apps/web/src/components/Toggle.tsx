import type { ReactNode } from 'react'
import './Toggle.css'

export function Toggle({
  checked,
  onChange,
  label,
  description,
  disabled = false,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  description?: ReactNode
  disabled?: boolean
}) {
  return (
    <label className={`switch-row ${disabled ? 'disabled' : ''}`}>
      <span className="switch-text">
        <b>{label}</b>
        {description && <small>{description}</small>}
      </span>
      <input
        type="checkbox"
        role="switch"
        className="sr-only"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span className={`switch ${checked ? 'on' : ''}`} aria-hidden="true">
        {checked ? '[●  ON]' : '[OFF  ○]'}
      </span>
    </label>
  )
}

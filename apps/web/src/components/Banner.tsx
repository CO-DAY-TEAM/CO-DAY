import './Banner.css'

export function Banner({
  kind,
  message,
  onClose,
}: {
  kind: 'error' | 'ok'
  message: string
  onClose: () => void
}) {
  const error = kind === 'error'
  return (
    <div role={error ? 'alert' : 'status'} className={`banner ${error ? 'error' : ''}`}>
      <b>{error ? '✖ ERR' : '✔ OK'}</b>
      <span>{message}</span>
      <button aria-label="알림 닫기" onClick={onClose}>
        ×
      </button>
    </div>
  )
}

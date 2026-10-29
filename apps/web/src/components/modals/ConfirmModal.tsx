import { Modal } from './Modal'

export function ConfirmModal({
  message,
  confirmLabel,
  onCancel,
  onConfirm,
}: {
  message: string
  confirmLabel: string
  onCancel: () => void
  onConfirm: () => void
}) {
  return (
    <Modal title="? confirm --apply" onClose={onCancel}>
      <p className="modal-body">
        ? {message} <span className="muted">(y/N)</span>
      </p>
      <div className="modal-actions">
        <button className="button" onClick={onCancel}>
          취소
        </button>
        <button className="button primary" autoFocus onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}

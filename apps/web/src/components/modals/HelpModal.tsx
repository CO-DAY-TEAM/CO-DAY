import { Modal } from './Modal'
import './HelpModal.css'

const shortcuts = [
  ['1', '대시보드'],
  ['2', '레포지토리'],
  ['3', '설정'],
  ['/', '검색'],
  ['R', '새로고침'],
  ['?', '도움말'],
  ['Esc', '닫기'],
]

export function HelpModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="? shortcuts --help" onClose={onClose}>
      <div className="shortcut-list">
        {shortcuts.map(([key, label]) => (
          <span key={key}>
            <kbd>{key}</kbd> {label}
          </span>
        ))}
      </div>
    </Modal>
  )
}

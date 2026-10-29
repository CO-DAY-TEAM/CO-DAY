import { useEffect, useRef, useState } from 'react'
import type { User } from '../../api/types'

export function UserMenu({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // 메뉴 바깥을 누르거나 Esc를 누르면 닫는다
  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape' : !ref.current?.contains(event.target as Node))
        setOpen(false)
    }
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('mousedown', close)
      window.removeEventListener('keydown', close)
    }
  }, [open])

  return (
    <div className="user-wrap" ref={ref}>
      <button
        className="user-button"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
      >
        <span className="avatar">{user.login.slice(0, 2).toUpperCase()}</span>
        {user.login} ⌄
      </button>
      {open && (
        <div className="dropdown" role="menu" onClick={() => setOpen(false)}>
          <a role="menuitem" href={user.install_url} target="_blank" rel="noreferrer">
            저장소 연결 관리 <span>↗</span>
          </a>
          <button role="menuitem" onClick={onLogout}>
            로그아웃 <span>↪</span>
          </button>
        </div>
      )}
    </div>
  )
}

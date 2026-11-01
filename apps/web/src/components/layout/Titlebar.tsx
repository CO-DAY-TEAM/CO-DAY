import type { User } from '../../api/types'
import type { Theme } from '../../hooks/useTheme'
import { views } from '../../lib/constants'
import type { View } from '../../lib/constants'
import { Logo } from '../Logo'
import { UserMenu } from './UserMenu'
import './Titlebar.css'

export function Titlebar({
  user,
  view,
  onViewChange,
  theme,
  onThemeChange,
  onLogout,
}: {
  user: User
  view: View
  onViewChange: (view: View) => void
  theme: Theme
  onThemeChange: (theme: Theme) => void
  onLogout: () => void
}) {
  return (
    <header className="titlebar">
      <span className="traffic" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <a href="/" aria-label="CO-DAY 홈">
        <Logo />
      </a>
      <nav aria-label="주 메뉴">
        {views.map((item, index) => (
          <button
            key={item.key}
            className={view === item.key ? 'nav-active' : ''}
            aria-current={view === item.key ? 'page' : undefined}
            onClick={() => onViewChange(item.key)}
          >
            <kbd>{index + 1}</kbd> {item.label}
          </button>
        ))}
      </nav>
      <span className="title-path">
        {user.login}@co-day: ~/{view}
      </span>
      <div className="titlebar-actions">
        <button
          className="icon-button"
          aria-label={theme === 'dark' ? '라이트 테마로 변경' : '다크 테마로 변경'}
          title="테마 변경"
          onClick={() => onThemeChange(theme === 'dark' ? 'light' : 'dark')}
        >
          {theme === 'dark' ? '☼' : '☾'}
        </button>
        <UserMenu user={user} onLogout={onLogout} />
      </div>
    </header>
  )
}

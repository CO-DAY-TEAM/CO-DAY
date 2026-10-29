import { Logo } from '../../components/Logo'
import './AuthLoading.css'

export function AuthLoading() {
  return (
    <main className="auth-loading">
      <Logo />
      <p>
        <span className="accent">⠋</span> 로그인을 확인하고 있습니다…
        <span className="cursor">▍</span>
      </p>
    </main>
  )
}

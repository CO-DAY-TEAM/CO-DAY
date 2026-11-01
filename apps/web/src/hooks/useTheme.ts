import { useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'

function savedTheme(): Theme {
  try {
    return localStorage.getItem('co-day-theme') === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(savedTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem('co-day-theme', theme)
    } catch {
      // 저장하지 못해도 이번 화면에서는 테마가 적용된다
    }
  }, [theme])

  return [theme, setTheme] as const
}

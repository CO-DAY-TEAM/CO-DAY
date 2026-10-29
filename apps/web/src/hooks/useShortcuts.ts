import { useEffect } from 'react'

function isTyping(target: EventTarget | null) {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  )
}

// 입력 중이거나 모달이 열려 있을 때는 단축키를 무시한다
export function useShortcuts(
  enabled: boolean,
  onKey: (event: KeyboardEvent) => void,
) {
  // 매 렌더마다 다시 등록해서 onKey가 항상 최신 state를 보도록 한다
  useEffect(() => {
    if (!enabled) return
    const listener = (event: KeyboardEvent) => {
      if (isTyping(event.target)) return
      if (event.ctrlKey || event.metaKey || event.altKey) return
      if (document.querySelector('[aria-modal="true"]')) return
      onKey(event)
    }
    window.addEventListener('keydown', listener)
    return () => window.removeEventListener('keydown', listener)
  })
}

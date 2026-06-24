import { useEffect, useRef, useState } from "react"

/* Возвращает значение, обновляющееся не чаще одного раза в `ms`.
   Нужен, чтобы списки не рефетчили данные на КАЖДОЕ событие SSE
   (feed растёт постоянно при активном офисе). */
export function useThrottled<T>(value: T, ms: number): T {
  const [throttled, setThrottled] = useState(value)
  const last = useRef(0)
  const timer = useRef<ReturnType<typeof setTimeout>>()

  useEffect(() => {
    const now = Date.now()
    const remaining = ms - (now - last.current)
    if (remaining <= 0) {
      last.current = now
      setThrottled(value)
    } else {
      clearTimeout(timer.current)
      timer.current = setTimeout(() => { last.current = Date.now(); setThrottled(value) }, remaining)
    }
    return () => clearTimeout(timer.current)
  }, [value, ms])

  return throttled
}

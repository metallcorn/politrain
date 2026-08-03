import { useEffect, useState } from 'react'

// Unified generation loading screen (progress bar + rotating step text), matching the
// daily/bonus session loader so the exam doesn't feel different (feedback #191/#194/#195).
export default function GenLoader({
  icon,
  title,
  subtitle,
  steps = ['Готовим...', 'Генерируем...', 'Финальная проверка качества...'],
  barColor = 'bg-primary-500',
  bgColor = 'bg-primary-50',
  durationMs = 12000,
}) {
  const [progress, setProgress] = useState(0)
  const [step, setStep] = useState(0)

  useEffect(() => {
    const start = Date.now()
    const stepInterval = durationMs / steps.length
    const id = setInterval(() => {
      const elapsed = Date.now() - start
      // ease toward 95% (never 100 until the real load finishes)
      setProgress(Math.min(95, (elapsed / durationMs) * 100))
      setStep(Math.min(Math.floor(elapsed / stepInterval), steps.length - 1))
    }, 150)
    return () => clearInterval(id)
  }, [durationMs, steps.length])

  return (
    <div className="flex flex-col items-center gap-6 py-12 text-center px-4">
      <div className={`w-20 h-20 rounded-full ${bgColor} flex items-center justify-center`}>
        {icon}
      </div>
      <div>
        <h2 className="text-xl font-bold text-gray-900">{title}</h2>
        {subtitle && <p className="text-gray-500 text-sm mt-2">{subtitle}</p>}
      </div>
      <div className="w-full max-w-xs">
        <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
          <div className={`h-full ${barColor} rounded-full transition-all duration-200 ease-out`}
               style={{ width: `${progress}%` }} />
        </div>
      </div>
      <p className="text-sm text-gray-400 animate-pulse min-h-5">{steps[step]}</p>
    </div>
  )
}

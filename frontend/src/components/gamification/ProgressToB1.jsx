import ProgressBar from '../ui/ProgressBar'

// Dynamic "progress to your next level" (target from the backend — B1, B2, …).
// At 100% mastery of the next level, auto-promotion kicks in on your next correct answer.
export default function ProgressToB1({ progress, target }) {
  const label = target ? `Прогресс к ${target}` : 'Прогресс к следующему уровню'
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-600">{label}</span>
        <span className="text-sm font-bold text-primary-800">{Math.round(progress)}%</span>
      </div>
      <ProgressBar value={progress} max={100} />
      <p className="text-xs text-gray-400 mt-1">
        {progress < 100
          ? `Освой ещё ${Math.round(100 - progress)}% тем ${target || ''} — и уровень повысится сам`
          : `Готово! Уровень повысится на ${target}`}
      </p>
    </div>
  )
}

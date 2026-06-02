import ProgressBar from '../ui/ProgressBar'

export default function ProgressToB1({ progress }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-gray-600">Прогресс к B1</span>
        <span className="text-sm font-bold text-primary-800">{Math.round(progress)}%</span>
      </div>
      <ProgressBar value={progress} max={100} />
      <p className="text-xs text-gray-400 mt-1">{progress < 100 ? `${Math.round(100 - progress)}% осталось` : 'Готов к экзамену!'}</p>
    </div>
  )
}

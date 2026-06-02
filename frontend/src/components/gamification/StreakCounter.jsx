import { Flame } from 'lucide-react'

export default function StreakCounter({ days }) {
  return (
    <div className="flex items-center gap-1.5">
      <Flame size={16} className={days > 0 ? 'text-orange-500' : 'text-gray-300'} />
      <span className={`text-sm font-semibold ${days > 0 ? 'text-orange-500' : 'text-gray-400'}`}>
        {days}
      </span>
    </div>
  )
}

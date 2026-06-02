import { Zap } from 'lucide-react'

export default function XPBar({ xp }) {
  return (
    <div className="flex items-center gap-2">
      <Zap size={16} className="text-yellow-500" />
      <span className="text-sm font-semibold text-gray-700">{xp} XP</span>
    </div>
  )
}

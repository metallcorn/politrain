import { Zap } from 'lucide-react'

export default function Leaderboard({ data }) {
  if (!data || !data.entries?.length) return null

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-400 uppercase tracking-wide">Сегодня в рейтинге</p>
        <p className="text-xs text-gray-400">#{data.my_rank} из {data.total_users}</p>
      </div>
      <div className="flex flex-col gap-0.5">
        {data.entries.map((e) => (
          <div
            key={e.rank}
            className={`flex items-center gap-2 px-2 py-1.5 rounded-lg ${
              e.is_current_user ? 'bg-primary-50 border border-primary-200' : ''
            }`}
          >
            <span className="text-xs text-gray-400 w-5 text-right font-mono leading-none">
              {e.rank}
            </span>
            <span
              className={`flex-1 text-sm leading-none ${
                e.is_current_user ? 'font-bold text-primary-700' : 'text-gray-700'
              }`}
            >
              {e.username}
            </span>
            <div className="flex items-center gap-0.5">
              <Zap size={11} className="text-yellow-500" />
              <span className="text-xs font-semibold text-gray-700">{e.xp_today}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ActivityHeatmap({ activity }) {
  const today = new Date()
  const days = []
  for (let i = 364; i >= 0; i--) {
    const d = new Date(today)
    d.setDate(d.getDate() - i)
    const key = d.toISOString().split('T')[0]
    const entry = activity?.find((a) => a.date === key)
    days.push({ date: key, xp: entry?.xp_earned || 0 })
  }

  const getColor = (xp) => {
    if (xp === 0) return 'bg-gray-100'
    if (xp < 50) return 'bg-primary-200'
    if (xp < 150) return 'bg-primary-400'
    return 'bg-primary-800'
  }

  const weeks = []
  for (let i = 0; i < days.length; i += 7) {
    weeks.push(days.slice(i, i + 7))
  }

  return (
    <div className="w-full overflow-x-auto">
      <div className="flex gap-0.5 min-w-max">
        {weeks.map((week, wi) => (
          <div key={wi} className="flex flex-col gap-0.5">
            {week.map((day) => (
              <div
                key={day.date}
                className={`w-3 h-3 rounded-sm ${getColor(day.xp)}`}
                title={`${day.date}: ${day.xp} XP`}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

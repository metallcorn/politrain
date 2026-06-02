export default function AchievementBadge({ achievement, earned }) {
  return (
    <div className={`flex flex-col items-center gap-1 p-3 rounded-xl border transition-all ${
      earned ? 'border-yellow-200 bg-yellow-50' : 'border-gray-100 bg-gray-50 opacity-50'
    }`}>
      <span className="text-2xl">{achievement.icon || '🏅'}</span>
      <span className="text-xs font-medium text-center text-gray-700 leading-tight">
        {achievement.title_ru}
      </span>
      {earned && <span className="text-xs text-yellow-600">+{achievement.xp_reward} XP</span>}
    </div>
  )
}

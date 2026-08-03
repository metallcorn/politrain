import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { profileApi } from '../api'
import AchievementBadge from '../components/gamification/AchievementBadge'
import Skeleton from '../components/ui/Skeleton'
import { ArrowLeft } from 'lucide-react'

export default function AchievementsPage() {
  const [achievements, setAchievements] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    profileApi.achievements()
      .then((r) => setAchievements(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const earned = achievements
    .filter((a) => a.earned)
    .sort((a, b) => new Date(b.earned_at || 0) - new Date(a.earned_at || 0))
  const locked = achievements.filter((a) => !a.earned)

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/profile')} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-2xl font-bold text-gray-900">Достижения</h1>
        {!loading && (
          <span className="ml-auto text-sm font-medium text-gray-500">{earned.length}/{achievements.length}</span>
        )}
      </div>

      {loading ? (
        <div className="grid grid-cols-3 gap-2">
          {Array.from({ length: 12 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}
        </div>
      ) : (
        <>
          {earned.length > 0 && (
            <div>
              <h2 className="font-semibold text-gray-800 mb-3">Получено ({earned.length})</h2>
              <div className="grid grid-cols-3 gap-2">
                {earned.map((a) => <AchievementBadge key={a.id} achievement={a} earned />)}
              </div>
            </div>
          )}
          {locked.length > 0 && (
            <div>
              <h2 className="font-semibold text-gray-800 mb-3">Ещё впереди ({locked.length})</h2>
              <div className="grid grid-cols-3 gap-2">
                {locked.map((a) => <AchievementBadge key={a.id} achievement={a} earned={false} />)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

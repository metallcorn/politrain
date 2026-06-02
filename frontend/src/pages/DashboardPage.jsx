import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuthStore } from '../store'
import { profileApi, trainingApi, vocabApi } from '../api'
import Card from '../components/ui/Card'
import ProgressToB1 from '../components/gamification/ProgressToB1'
import StreakCounter from '../components/gamification/StreakCounter'
import Skeleton from '../components/ui/Skeleton'
import { BookOpen, Dumbbell, MessageSquare, AlertTriangle, Zap } from 'lucide-react'

export default function DashboardPage() {
  const { user } = useAuthStore()
  const [profile, setProfile] = useState(null)
  const [trainingStats, setTrainingStats] = useState(null)
  const [vocabStats, setVocabStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      profileApi.get(),
      trainingApi.stats(),
      vocabApi.stats(),
    ]).then(([p, t, v]) => {
      setProfile(p.data)
      setTrainingStats(t.data)
      setVocabStats(v.data)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-24 rounded" />
          <Skeleton className="h-7 w-40 rounded-lg" />
        </div>
        <div className="flex gap-2">
          <Skeleton className="h-7 w-14 rounded-lg" />
          <Skeleton className="h-7 w-14 rounded-lg" />
        </div>
      </div>
      <Skeleton className="h-20" />
      <Skeleton className="h-4 w-40 rounded mt-1" />
      {[1,2,3].map(i => (
        <div key={i} className="bg-white rounded-2xl border border-gray-100 p-4 flex items-center gap-3">
          <Skeleton className="w-10 h-10 flex-shrink-0" />
          <div className="flex flex-col gap-2 flex-1">
            <Skeleton className="h-4 w-36 rounded" />
            <Skeleton className="h-3 w-24 rounded" />
          </div>
        </div>
      ))}
    </div>
  )

  const timeOfDay = () => {
    const h = new Date().getHours()
    if (h < 12) return 'Доброе утро'
    if (h < 18) return 'Добрый день'
    return 'Добрый вечер'
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-500 text-sm">{timeOfDay()},</p>
          <h1 className="text-2xl font-bold text-gray-900">{user?.username} 👋</h1>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <Zap size={16} className="text-yellow-500" />
            <span className="font-bold text-gray-700">{user?.xp}</span>
          </div>
          <StreakCounter days={user?.streak_days} />
        </div>
      </div>

      {profile && <ProgressToB1 progress={profile.progress_to_b1} />}

      {/* Weak spots */}
      {profile?.weak_spots?.length > 0 && (
        <Card className="border-orange-100">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={18} className="text-orange-500" />
            <h2 className="font-semibold text-gray-800">Рекомендуем повторить</h2>
          </div>
          <div className="flex flex-col gap-2">
            {profile.weak_spots.map((ws) => (
              <Link key={ws.topic_slug} to={`/topics/${ws.topic_slug}`} className="flex items-center justify-between py-2 hover:bg-gray-50 rounded-lg px-2 transition-colors">
                <span className="text-sm text-gray-700">{ws.title_ru}</span>
                <span className="text-sm font-semibold text-orange-600">{ws.score}%</span>
              </Link>
            ))}
          </div>
        </Card>
      )}

      {/* Today's plan */}
      <h2 className="font-semibold text-gray-800 mt-2">Что делать сегодня</h2>
      <div className="grid grid-cols-1 gap-3">
        {vocabStats?.due_today > 0 && (
          <Link to="/training?mode=daily">
            <Card className="border-blue-100 hover:border-blue-300 transition-colors">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-blue-50 rounded-xl flex items-center justify-center">
                  <BookOpen size={20} className="text-blue-600" />
                </div>
                <div>
                  <p className="font-medium text-gray-800">Слова на повторение</p>
                  <p className="text-sm text-gray-500">{vocabStats.due_today} слов ждут</p>
                </div>
              </div>
            </Card>
          </Link>
        )}

        <Link to="/training">
          <Card className="hover:border-primary-300 transition-colors">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-primary-50 rounded-xl flex items-center justify-center">
                <Dumbbell size={20} className="text-primary-800" />
              </div>
              <div>
                <p className="font-medium text-gray-800">Дневная тренировка</p>
                <p className="text-sm text-gray-500">
                  {trainingStats?.today_done || 0}/{trainingStats?.today_total || 0} заданий выполнено
                </p>
              </div>
            </div>
          </Card>
        </Link>

        <Link to="/chat">
          <Card className="hover:border-green-300 transition-colors">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-green-50 rounded-xl flex items-center justify-center">
                <MessageSquare size={20} className="text-green-600" />
              </div>
              <div>
                <p className="font-medium text-gray-800">Поговори по-польски</p>
                <p className="text-sm text-gray-500">Свободный разговор с AI</p>
              </div>
            </div>
          </Card>
        </Link>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mt-2">
        <Card className="text-center py-3">
          <p className="text-xl font-bold text-primary-800">{profile?.total_exercises || 0}</p>
          <p className="text-xs text-gray-500 mt-0.5">Упражнений</p>
        </Card>
        <Card className="text-center py-3">
          <p className="text-xl font-bold text-primary-800">{profile?.vocab_count || 0}</p>
          <p className="text-xs text-gray-500 mt-0.5">Слов</p>
        </Card>
        <Card className="text-center py-3">
          <p className="text-xl font-bold text-primary-800">{profile?.total_chat_messages || 0}</p>
          <p className="text-xs text-gray-500 mt-0.5">Сообщений</p>
        </Card>
      </div>
    </div>
  )
}

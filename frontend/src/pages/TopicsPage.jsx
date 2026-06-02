import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { topicsApi } from '../api'
import { useAuthStore } from '../store'
import Card from '../components/ui/Card'
import Skeleton from '../components/ui/Skeleton'
import { Lock, CheckCircle, Clock, AlertCircle } from 'lucide-react'

const LEVELS = ['A0', 'A1', 'A2', 'B1']
const STATUS_ICON = {
  locked: <Lock size={16} className="text-gray-300" />,
  available: <div className="w-4 h-4 rounded-full border-2 border-primary-400" />,
  in_progress: <Clock size={16} className="text-blue-500" />,
  done: <CheckCircle size={16} className="text-green-500" />,
  needs_review: <AlertCircle size={16} className="text-orange-500" />,
}

export default function TopicsPage() {
  const [topics, setTopics] = useState([])
  const [loading, setLoading] = useState(true)
  const { user } = useAuthStore()
  const lang = user?.native_language || 'ru'

  useEffect(() => {
    topicsApi.list().then((r) => setTopics(r.data)).finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex flex-col gap-6 animate-fade-in">
      <Skeleton className="h-8 w-32 rounded-lg" />
      {[4, 3, 3].map((count, gi) => (
        <div key={gi} className="flex flex-col gap-3">
          <div className="flex items-center justify-between mb-1">
            <Skeleton className="h-5 w-12 rounded" />
            <Skeleton className="h-3 w-20 rounded" />
          </div>
          {Array.from({ length: count }).map((_, i) => (
            <div key={i} className="bg-white rounded-2xl border border-gray-100 p-4 flex items-center gap-3">
              <Skeleton className="w-8 h-8 flex-shrink-0 rounded-lg" />
              <div className="flex flex-col gap-1.5 flex-1">
                <Skeleton className="h-4 w-3/4 rounded" />
                <Skeleton className="h-3 w-1/2 rounded" />
              </div>
              <Skeleton className="w-4 h-4 rounded-full flex-shrink-0" />
            </div>
          ))}
        </div>
      ))}
    </div>
  )

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-gray-900">Правила</h1>

      {LEVELS.map((level) => {
        const levelTopics = topics.filter((t) => t.level_required === level)
        if (levelTopics.length === 0) return null
        const done = levelTopics.filter((t) => t.status === 'done').length
        return (
          <div key={level}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-800">Уровень {level}</h2>
              <span className="text-sm text-gray-500">{done}/{levelTopics.length}</span>
            </div>
            <div className="flex flex-col gap-2">
              {levelTopics.map((topic) => (
                <Link
                  key={topic.slug}
                  to={topic.status === 'locked' ? '#' : `/topics/${topic.slug}`}
                  onClick={(e) => topic.status === 'locked' && e.preventDefault()}
                >
                  <Card className={`flex items-center gap-3 transition-all ${
                    topic.status === 'locked' ? 'opacity-50 cursor-not-allowed' : 'hover:border-primary-200 cursor-pointer'
                  }`}>
                    <div className="flex-shrink-0">
                      {STATUS_ICON[topic.status] || STATUS_ICON.locked}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-gray-800 truncate">
                        {lang === 'ru' ? topic.title_ru : topic.title_en}
                      </p>
                      {topic.score > 0 && (
                        <div className="w-full bg-gray-100 rounded-full h-1 mt-1">
                          <div
                            className="h-full bg-green-500 rounded-full"
                            style={{ width: `${topic.score * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                    {topic.score > 0 && (
                      <span className="text-xs text-gray-400 flex-shrink-0">
                        {Math.round(topic.score * 100)}%
                      </span>
                    )}
                  </Card>
                </Link>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

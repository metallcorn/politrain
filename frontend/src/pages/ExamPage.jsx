import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { examApi } from '../api'
import { useAuthStore } from '../store'
import Card from '../components/ui/Card'
import Spinner from '../components/ui/Spinner'
import { Lock } from 'lucide-react'

export default function ExamPage() {
  const [tasks, setTasks] = useState([])
  const [unlocked, setUnlocked] = useState(false)
  const [loading, setLoading] = useState(true)
  const { user } = useAuthStore()

  useEffect(() => {
    examApi.tasks().then((r) => {
      setTasks(r.data.tasks)
      setUnlocked(r.data.unlocked)
    }).finally(() => setLoading(false))
  }, [])

  const lang = user?.native_language || 'ru'

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Экзамен B1</h1>
        <p className="text-gray-500 text-sm mt-0.5">Подготовка к официальному экзамену</p>
      </div>

      {!unlocked && (
        <div className="card bg-orange-50 border-orange-100">
          <div className="flex items-center gap-3">
            <Lock size={20} className="text-orange-500" />
            <div>
              <p className="font-medium text-orange-800">Требуется уровень A2</p>
              <p className="text-sm text-orange-600 mt-0.5">Пройди темы уровней A0-A2 чтобы разблокировать экзамен</p>
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-3">
        {tasks.map((task) => {
          const isAvailable = unlocked && task.available
          const title = lang === 'ru' ? task.title_ru : task.title_en
          const desc = lang === 'ru' ? task.description_ru : task.description_en

          return (
            <Link key={task.type} to={isAvailable ? `/exam/${task.type}` : '#'} onClick={(e) => !isAvailable && e.preventDefault()}>
              <Card className={`flex items-center gap-4 transition-all ${
                isAvailable ? 'hover:border-primary-200 cursor-pointer' : 'opacity-60 cursor-not-allowed'
              }`}>
                <div>
                  <p className="font-semibold text-gray-800">{title}</p>
                  <p className="text-sm text-gray-500 mt-0.5">{desc}</p>
                </div>
                {(!task.available || !unlocked) && <Lock size={16} className="text-gray-300 ml-auto flex-shrink-0" />}
              </Card>
            </Link>
          )
        })}
      </div>
    </div>
  )
}

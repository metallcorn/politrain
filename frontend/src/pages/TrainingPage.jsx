import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { trainingApi, vocabApi } from '../api'
import Card from '../components/ui/Card'
import Skeleton from '../components/ui/Skeleton'
import { Calendar, AlertCircle, Sparkles, Rocket, BookOpen, RefreshCw } from 'lucide-react'

export default function TrainingPage() {
  const [stats, setStats] = useState(null)
  const [vocabStats, setVocabStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.allSettled([
      trainingApi.stats(),
      vocabApi.stats(),
    ]).then(([t, v]) => {
      if (t.status === 'fulfilled') setStats(t.value.data)
      if (v.status === 'fulfilled') setVocabStats(v.value.data)
    }).finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex flex-col gap-5 animate-fade-in">
      <div className="flex flex-col gap-1">
        <Skeleton className="h-8 w-36 rounded-lg" />
        <Skeleton className="h-4 w-52 rounded" />
      </div>
      {[1,2,3,4].map(i => (
        <div key={i} className="bg-white rounded-2xl border-2 border-gray-100 p-4 flex items-start gap-4">
          <Skeleton className="w-12 h-12 flex-shrink-0 rounded-xl" />
          <div className="flex flex-col gap-2 flex-1">
            <Skeleton className="h-5 w-40 rounded" />
            <Skeleton className="h-3 w-full rounded" />
            <Skeleton className="h-3 w-24 rounded" />
          </div>
        </div>
      ))}
    </div>
  )

  const dailyDone = stats?.today_total > 0 && stats?.today_done >= stats?.today_total

  const modes = [
    {
      mode: 'daily',
      disabled: false,
      icon: <Calendar size={28} className="text-primary-800" />,
      title: 'Дневная сессия',
      description: 'Смешанный набор: новое, повторение, слабые места',
      count: stats
        ? dailyDone
          ? '✓ Выполнено сегодня'
          : stats.today_total > 0
            ? `осталось ${stats.today_total - stats.today_done} из ${stats.today_total}`
            : 'Начать'
        : '...',
      color: 'border-primary-100 hover:border-primary-300',
      badge: null,
    },
    {
      mode: 'bonus',
      disabled: !dailyDone,
      icon: <Rocket size={28} className={dailyDone ? 'text-purple-500' : 'text-gray-300'} />,
      title: 'Бонусная сессия',
      description: dailyDone
        ? 'Свежие задания сверх дневной нормы — генерируются специально для тебя'
        : 'Доступна после выполнения дневной сессии',
      count: dailyDone ? 'Дневная выполнена ✓' : 'Сначала пройди дневную',
      color: dailyDone
        ? 'border-purple-100 hover:border-purple-300'
        : 'border-gray-100 opacity-50',
      badge: null,
    },
    {
      mode: 'errors',
      disabled: false,
      icon: <AlertCircle size={28} className="text-red-500" />,
      title: 'Работа над ошибками',
      description: 'Только задания которые ты раньше сделал неправильно',
      count: `${stats?.errors || 0} заданий`,
      color: 'border-red-100 hover:border-red-300',
      badge: stats?.errors > 0 ? stats.errors : null,
    },
    {
      mode: 'new',
      disabled: false,
      icon: <Sparkles size={28} className="text-yellow-500" />,
      title: 'Только новое',
      description: 'Только свежий материал без повторений',
      count: 'Новые задания',
      color: 'border-yellow-100 hover:border-yellow-300',
      badge: null,
    },
    {
      mode: 'vocab',
      disabled: false,
      icon: <BookOpen size={28} className="text-blue-500" />,
      title: 'Слова',
      description: 'Учи польские слова — карточки с переводом',
      count: vocabStats
        ? vocabStats.known_count > 0
          ? `${vocabStats.known_count} слов знаешь${vocabStats.due_count > 0 ? ` · ${vocabStats.due_count} на повторение` : ''}`
          : 'Начни изучать слова'
        : '...',
      color: 'border-blue-100 hover:border-blue-300',
      badge: vocabStats?.due_count > 0 ? vocabStats.due_count : null,
    },
    {
      mode: 'practice',
      disabled: false,
      icon: <RefreshCw size={28} className="text-teal-500" />,
      title: 'Повторение',
      description: 'Случайная подборка пройденного материала — без лимита в день',
      count: 'Закрепи пройденное',
      color: 'border-teal-100 hover:border-teal-300',
      badge: null,
    },
  ]

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Тренировка</h1>
        <p className="text-gray-500 text-sm mt-1">Выбери режим занятий</p>
      </div>

      <div className="flex flex-col gap-4">
        {modes.map(({ mode, disabled, icon, title, description, count, color, badge }) => {
          const card = (
            <Card className={`border-2 transition-colors ${color} relative`}>
              {badge && (
                <span className="absolute top-3 right-3 bg-red-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center">
                  {badge}
                </span>
              )}
              <div className="flex items-start gap-4">
                <div className="p-2 rounded-xl bg-gray-50">{icon}</div>
                <div>
                  <h2 className="font-semibold text-gray-900">{title}</h2>
                  <p className="text-sm text-gray-500 mt-0.5">{description}</p>
                  <p className="text-xs text-gray-400 mt-1">{count}</p>
                </div>
              </div>
            </Card>
          )
          return disabled
            ? <div key={mode}>{card}</div>
            : <Link key={mode} to={`/training/session?mode=${mode}`}>{card}</Link>
        })}
      </div>

      {/* Global stats */}
      <div className="card mt-2">
        <h2 className="font-semibold text-gray-800 mb-3">Статистика</h2>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <p className="text-xl font-bold text-gray-900">{stats?.total_exercises || 0}</p>
            <p className="text-xs text-gray-500">Всего</p>
          </div>
          <div className="text-center">
            <p className="text-xl font-bold text-green-600">{stats?.correct || 0}</p>
            <p className="text-xs text-gray-500">Верно</p>
          </div>
          <div className="text-center">
            <p className="text-xl font-bold text-gray-700">{stats?.accuracy || 0}%</p>
            <p className="text-xs text-gray-500">Точность</p>
          </div>
        </div>
      </div>
    </div>
  )
}

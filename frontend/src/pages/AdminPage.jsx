import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../store'
import api from '../api'
import { adminApi } from '../api'
import Spinner from '../components/ui/Spinner'
import Button from '../components/ui/Button'
import { ArrowLeft, CheckCircle, Trash2, RefreshCw, Users, AlertCircle, MessageSquare, BarChart2 } from 'lucide-react'
import MistralUsageChart from '../components/admin/MistralUsageChart'

const TYPE_LABELS = {
  fill_blank: 'Заполни пропуск',
  multiple_choice: 'Выбор ответа',
  translate: 'Перевод',
  order_words: 'Порядок слов',
  flashcard: 'Карточка',
  judge_sentence: 'Верно/нет',
}

export default function AdminPage() {
  const { user } = useAuthStore()
  const navigate = useNavigate()
  const [tab, setTab] = useState('reports')
  const [reports, setReports] = useState([])
  const [users, setUsers] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showResolved, setShowResolved] = useState(false)
  const [actionId, setActionId] = useState(null)
  const [feedback, setFeedback] = useState([])
  const [showResolvedFeedback, setShowResolvedFeedback] = useState(false)

  const isAdmin = user?.is_admin

  useEffect(() => {
    if (!isAdmin) { navigate('/profile'); return }
    loadData()
  }, [showResolved, showResolvedFeedback])

  const loadData = async () => {
    setLoading(true)
    try {
      const [r, s, u, fb] = await Promise.all([
        api.get(`/admin/reports?resolved=${showResolved}`),
        api.get('/admin/stats'),
        api.get('/admin/users'),
        adminApi.getFeedback(showResolvedFeedback),
      ])
      setReports(r.data)
      setStats(s.data)
      setUsers(u.data)
      setFeedback(fb.data)
    } catch (e) {
      console.error('Admin load error:', e)
    } finally {
      setLoading(false)
    }
  }

  const resolve = async (id) => {
    setActionId(id)
    try {
      await api.post(`/admin/reports/${id}/resolve`)
      setReports((r) => r.filter((x) => x.id !== id))
    } finally {
      setActionId(null)
    }
  }

  const removeReport = async (id) => {
    setActionId(id)
    try {
      await api.delete(`/admin/reports/${id}`)
      setReports((r) => r.filter((x) => x.id !== id))
    } finally {
      setActionId(null)
    }
  }

  const deleteUser = async (id, username) => {
    if (!confirm(`Удалить пользователя ${username}?`)) return
    setActionId(id)
    try {
      await api.delete(`/admin/users/${id}`)
      setUsers((u) => u.filter((x) => x.id !== id))
      setStats((s) => s ? { ...s, total_users: s.total_users - 1 } : s)
    } finally {
      setActionId(null)
    }
  }

  const resolveFeedback = async (id) => {
    setActionId(id)
    try {
      await adminApi.resolveFeedback(id)
      setFeedback((f) => f.filter((x) => x.id !== id))
    } finally {
      setActionId(null)
    }
  }

  if (!isAdmin) return null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/profile')} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-bold text-gray-900">Панель администратора</h1>
        <button onClick={loadData} className="ml-auto text-gray-400 hover:text-gray-600">
          <RefreshCw size={16} />
        </button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3">
          <div className="card text-center py-3">
            <p className="text-2xl font-bold text-primary-800">{stats.total_users}</p>
            <p className="text-xs text-gray-500">Пользователей</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-2xl font-bold text-orange-500">{stats.open_reports}</p>
            <p className="text-xs text-gray-500">Открытых жалоб</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-2xl font-bold text-gray-700">{stats.total_reports}</p>
            <p className="text-xs text-gray-500">Всего жалоб</p>
          </div>
          <div className="card text-center py-3">
            <p className="text-2xl font-bold text-green-600">{stats.total_exercises_done}</p>
            <p className="text-xs text-gray-500">Пройдено заданий</p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-200">
        <button
          onClick={() => setTab('reports')}
          className={`flex items-center gap-1.5 pb-2 text-sm font-medium border-b-2 transition-colors ${
            tab === 'reports' ? 'border-primary-800 text-primary-800' : 'border-transparent text-gray-500'
          }`}
        >
          <AlertCircle size={15} />
          Жалобы
          {stats?.open_reports > 0 && (
            <span className="bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
              {stats.open_reports}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab('users')}
          className={`flex items-center gap-1.5 pb-2 text-sm font-medium border-b-2 transition-colors ${
            tab === 'users' ? 'border-primary-800 text-primary-800' : 'border-transparent text-gray-500'
          }`}
        >
          <Users size={15} />
          Пользователи
        </button>
        <button
          onClick={() => setTab('feedback')}
          className={`flex items-center gap-1.5 pb-2 text-sm font-medium border-b-2 transition-colors ${
            tab === 'feedback' ? 'border-primary-800 text-primary-800' : 'border-transparent text-gray-500'
          }`}
        >
          <MessageSquare size={15} />
          Фидбэк
          {feedback.filter((f) => !f.is_resolved).length > 0 && (
            <span className="bg-blue-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
              {feedback.filter((f) => !f.is_resolved).length}
            </span>
          )}
        </button>
        <button
          onClick={() => setTab('mistral')}
          className={`flex items-center gap-1.5 pb-2 text-sm font-medium border-b-2 transition-colors ${
            tab === 'mistral' ? 'border-primary-800 text-primary-800' : 'border-transparent text-gray-500'
          }`}
        >
          <BarChart2 size={15} />
          API
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : tab === 'reports' ? (
        <>
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-800">
              {showResolved ? 'Решённые' : 'Открытые'} жалобы
              <span className="ml-2 text-sm font-normal text-gray-400">({reports.length})</span>
            </h2>
            <button
              onClick={() => setShowResolved((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              {showResolved ? 'Показать открытые' : 'Показать решённые'}
            </button>
          </div>

          {reports.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <CheckCircle size={40} className="mx-auto mb-2 text-green-400" />
              <p>Нет жалоб</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {reports.map((r) => (
                <div key={r.id} className="card flex flex-col gap-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                        {TYPE_LABELS[r.exercise?.type] || r.exercise?.type}
                      </span>
                      <span className="text-xs text-gray-400">{r.level} · #{r.id}</span>
                    </div>
                    <span className="text-xs text-gray-400 flex-shrink-0">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString('ru') : ''}
                    </span>
                  </div>

                  <div className="bg-gray-50 rounded-xl p-3 text-sm">
                    <p className="font-medium text-gray-800 mb-1">{r.exercise?.question}</p>
                    {r.exercise?.options && (
                      <p className="text-gray-500 text-xs">Варианты: {r.exercise.options.join(' / ')}</p>
                    )}
                    <p className="text-xs text-green-700 mt-1">✓ {r.exercise?.correct_answer}</p>
                  </div>

                  {r.comment && (
                    <div className="border-l-2 border-orange-300 pl-3">
                      <p className="text-sm text-gray-700">{r.comment}</p>
                    </div>
                  )}

                  {!showResolved && (
                    <div className="flex gap-2">
                      <Button
                        className="flex-1 text-sm"
                        onClick={() => resolve(r.id)}
                        loading={actionId === r.id}
                      >
                        <CheckCircle size={15} />
                        Принято к сведению
                      </Button>
                      <button
                        onClick={() => removeReport(r.id)}
                        disabled={actionId === r.id}
                        className="px-3 py-2 text-red-400 hover:text-red-600 transition-colors"
                        title="Удалить жалобу"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      ) : tab === 'feedback' ? (
        <>
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-800">
              {showResolvedFeedback ? 'Решённый' : 'Открытый'} фидбэк
              <span className="ml-2 text-sm font-normal text-gray-400">({feedback.length})</span>
            </h2>
            <button
              onClick={() => setShowResolvedFeedback((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              {showResolvedFeedback ? 'Показать открытые' : 'Показать решённые'}
            </button>
          </div>

          {feedback.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <CheckCircle size={40} className="mx-auto mb-2 text-green-400" />
              <p>Нет фидбэка</p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {feedback.map((f) => (
                <div key={f.id} className="card flex flex-col gap-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs text-gray-400">
                      #{f.id} · {f.created_at ? new Date(f.created_at).toLocaleDateString('ru') : ''}
                    </span>
                  </div>
                  {f.url && (
                    <p className="text-xs text-blue-500 truncate">{f.url}</p>
                  )}
                  <p className="text-sm text-gray-800">{f.comment}</p>
                  {f.page_snapshot && (
                    <details className="text-xs text-gray-400">
                      <summary className="cursor-pointer hover:text-gray-600">Снимок страницы</summary>
                      <pre className="mt-1 whitespace-pre-wrap bg-gray-50 rounded p-2 max-h-40 overflow-y-auto">{f.page_snapshot}</pre>
                    </details>
                  )}
                  {!showResolvedFeedback && (
                    <Button
                      className="text-sm"
                      onClick={() => resolveFeedback(f.id)}
                      loading={actionId === f.id}
                    >
                      <CheckCircle size={15} />
                      Принято к сведению
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      ) : tab === 'users' ? (
        <>
          <h2 className="font-semibold text-gray-800">
            Пользователи
            <span className="ml-2 text-sm font-normal text-gray-400">({users.length})</span>
          </h2>
          <div className="flex flex-col gap-2">
            {users.map((u) => (
              <div key={u.id} className="card flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-primary-800 text-white flex items-center justify-center font-bold flex-shrink-0">
                  {u.username[0].toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-800 truncate">{u.username}</p>
                  <p className="text-xs text-gray-500">
                    {u.level} · {u.xp} XP · {u.native_language}
                    {!u.onboarding_done && ' · не прошёл онбординг'}
                  </p>
                </div>
                <div className="text-xs text-gray-400 flex-shrink-0 text-right">
                  <p>{u.streak_days}🔥</p>
                  <p>{u.created_at ? new Date(u.created_at).toLocaleDateString('ru') : ''}</p>
                </div>
                {u.username !== user?.username && (
                  <button
                    onClick={() => deleteUser(u.id, u.username)}
                    disabled={actionId === u.id}
                    className="text-red-300 hover:text-red-500 transition-colors flex-shrink-0"
                    title="Удалить пользователя"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      ) : tab === 'mistral' ? (
        <MistralUsageChart />
      ) : null}
    </div>
  )
}

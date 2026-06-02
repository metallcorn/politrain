import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { topicsApi } from '../api'
import { useAuthStore, useUIStore } from '../store'
import Button from '../components/ui/Button'
import Skeleton from '../components/ui/Skeleton'
import MultipleChoice from '../components/training/MultipleChoice'
import FillBlank from '../components/training/FillBlank'
import { trainingApi } from '../api'
import { ArrowLeft, RefreshCw, CheckCircle, Flag, Brain } from 'lucide-react'

function parseTable(block) {
  const rows = block.trim().split('\n')
  if (rows.length < 2) return null
  const isSep = (r) => /^\|[-| :]+\|$/.test(r.trim())
  const sepIdx = rows.findIndex(isSep)
  if (sepIdx < 1) return null

  const parseRow = (r) =>
    r.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())

  const headers = parseRow(rows[sepIdx - 1])
  const body = rows.slice(sepIdx + 1).filter((r) => r.trim().startsWith('|'))

  const th = headers.map((h) =>
    `<th class="px-3 py-2 text-left text-xs font-semibold text-gray-600 uppercase bg-gray-50 border-b border-gray-200">${inlineStyles(h)}</th>`
  ).join('')

  const trs = body.map((r) => {
    const cells = parseRow(r)
    const tds = cells.map((c) =>
      `<td class="px-3 py-2 text-sm text-gray-800 border-b border-gray-100">${inlineStyles(c)}</td>`
    ).join('')
    return `<tr class="hover:bg-gray-50">${tds}</tr>`
  }).join('')

  return `<div class="overflow-x-auto my-4 rounded-xl border border-gray-200"><table class="w-full border-collapse"><thead><tr>${th}</tr></thead><tbody>${trs}</tbody></table></div>`
}

function inlineStyles(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 text-primary-800 px-1 rounded text-xs font-mono">$1</code>')
}

function md(text) {
  if (!text) return ''

  // Extract and replace table blocks before any other processing
  text = text.replace(/((?:\|.+\|\n?)+)/g, (match) => {
    const html = parseTable(match)
    return html ?? match
  })

  return text
    .replace(/^### (.+)$/gm, '\x00h3\x01$1\x02')
    .replace(/^## (.+)$/gm, '\x00h2\x01$1\x02')
    .replace(/^# (.+)$/gm, '\x00h1\x01$1\x02')
    .replace(/^---+$/gm, '<hr class="my-4 border-gray-200"/>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em class="text-gray-700">$1</em>')
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 text-primary-800 px-1 rounded text-sm font-mono">$1</code>')
    .replace(/^- (.+)$/gm, '<li class="ml-5 list-disc leading-relaxed">$1</li>')
    .replace(/(<li[^>]*>.*?<\/li>\n?)+/g, (m) => `<ul class="my-2 space-y-1">${m}</ul>`)
    .replace(/\x00h3\x01(.+?)\x02/g, '<h3 class="text-base font-bold text-gray-900 mt-5 mb-1">$1</h3>')
    .replace(/\x00h2\x01(.+?)\x02/g, '<h2 class="text-lg font-bold text-gray-900 mt-5 mb-2">$1</h2>')
    .replace(/\x00h1\x01(.+?)\x02/g, '<h1 class="text-xl font-bold text-gray-900 mt-5 mb-2">$1</h1>')
    .replace(/\n{2,}/g, '</p><p class="mb-3 leading-relaxed">')
    .replace(/\n/g, '<br/>')
    .replace(/^/, '<p class="mb-3 leading-relaxed">')
    .replace(/$/, '</p>')
}

export default function TopicDetailPage() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const { addToast } = useUIStore()

  const [lesson, setLesson] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingExample, setLoadingExample] = useState(false)
  const [examples, setExamples] = useState([])
  const [exerciseResults, setExerciseResults] = useState({})
  const [completing, setCompleting] = useState(false)
  const [completed, setCompleted] = useState(false)
  const [reportingId, setReportingId] = useState(null)
  const [reportComment, setReportComment] = useState('')
  const [reportedIds, setReportedIds] = useState(new Set())

  useEffect(() => {
    topicsApi.getLesson(slug)
      .then((r) => {
        setLesson(r.data)
        const preResults = {}
        for (const ex of r.data.exercises || []) {
          if (ex.last_result) preResults[ex.id] = ex.last_result
        }
        setExerciseResults(preResults)
      })
      .catch(() => addToast('Ошибка загрузки урока', 'error'))
      .finally(() => setLoading(false))
  }, [slug])

  const loadNextExample = async () => {
    setLoadingExample(true)
    try {
      const r = await topicsApi.nextExample(slug)
      setExamples((ex) => [...ex, r.data.example])
    } catch {
      addToast('AI временно недоступен', 'error')
    } finally {
      setLoadingExample(false)
    }
  }

  const handleAnswer = async (exercise, userAnswer) => {
    try {
      const res = await trainingApi.answer({
        exercise_id: exercise.id,
        user_answer: userAnswer,
      })
      setExerciseResults((r) => ({ ...r, [exercise.id]: res.data }))
    } catch {
      addToast('Ошибка проверки ответа', 'error')
    }
  }

  const handleReport = async (exerciseId) => {
    try {
      await topicsApi.reportExercise(exerciseId, reportComment)
      setReportedIds((s) => new Set([...s, exerciseId]))
      setReportingId(null)
      setReportComment('')
      addToast('Спасибо! Ошибка записана', 'success')
    } catch {
      addToast('Ошибка отправки', 'error')
    }
  }

  const handleComplete = async () => {
    setCompleting(true)
    try {
      await topicsApi.complete(slug)
      setCompleted(true)
      addToast('Тема завершена! +50 XP', 'success')
    } catch {
      addToast('Ошибка', 'error')
    } finally {
      setCompleting(false)
    }
  }

  if (loading) return (
    <div className="flex flex-col gap-5 animate-fade-in">
      <div className="flex items-center gap-3">
        <Skeleton className="w-6 h-6 rounded-full" />
        <Skeleton className="h-7 w-48 rounded-lg" />
      </div>
      <div className="card flex flex-col gap-3">
        <Skeleton className="h-4 w-full rounded" />
        <Skeleton className="h-4 w-5/6 rounded" />
        <Skeleton className="h-4 w-4/6 rounded" />
        <Skeleton className="h-4 w-full rounded" />
        <Skeleton className="h-4 w-3/4 rounded" />
      </div>
      <Skeleton className="h-10 w-full rounded-xl" />
      <div className="flex flex-col gap-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="card flex flex-col gap-3">
            <Skeleton className="h-5 w-4/5 rounded" />
            <div className="grid grid-cols-1 gap-2">
              {[1, 2].map(j => <Skeleton key={j} className="h-10 w-full rounded-xl" />)}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
  if (!lesson) return <div className="text-center py-12 text-gray-500">Урок не найден</div>

  const lang = user?.native_language || 'ru'

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/topics')} className="text-gray-400 hover:text-gray-600 transition-colors">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-bold text-gray-900">{lesson.topic_title}</h1>
      </div>

      {/* Explanation */}
      <div className="card">
        <div
          className="text-gray-800 text-sm leading-relaxed"
          dangerouslySetInnerHTML={{ __html: md(lesson.explanation) }}
        />
      </div>

      {/* Extra examples */}
      {examples.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="font-semibold text-gray-800">Дополнительные примеры</h2>
          {examples.map((ex, i) => (
            <div key={i} className="card bg-blue-50 border-blue-100">
              <div
                className="text-sm text-gray-700 leading-relaxed"
                dangerouslySetInnerHTML={{ __html: md(ex) }}
              />
            </div>
          ))}
        </div>
      )}

      <Button variant="secondary" onClick={loadNextExample} loading={loadingExample} className="w-full">
        <RefreshCw size={16} />
        Ещё пример
      </Button>

      {/* Mini exercises */}
      {lesson.exercises?.length > 0 && (
        <div>
          <h2 className="font-semibold text-gray-800 mb-3">Мини-тест</h2>
          <div className="flex flex-col gap-4">
            {lesson.exercises.map((ex) => (
              <div key={ex.id} className="card">
                {ex.type === 'multiple_choice' ? (
                  <MultipleChoice
                    exercise={ex}
                    onAnswer={({ user_answer }) => handleAnswer(ex, user_answer)}
                    result={exerciseResults[ex.id]}
                  />
                ) : (
                  <FillBlank
                    exercise={ex}
                    onAnswer={({ user_answer }) => handleAnswer(ex, user_answer)}
                    result={exerciseResults[ex.id]}
                  />
                )}

                {/* Report error */}
                <div className="mt-3 pt-3 border-t border-gray-100">
                  {reportingId === ex.id ? (
                    <div className="flex flex-col gap-2">
                      <textarea
                        className="input resize-none h-16 text-sm"
                        placeholder="Опишите ошибку (необязательно)..."
                        value={reportComment}
                        onChange={(e) => setReportComment(e.target.value)}
                        autoFocus
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleReport(ex.id)}
                          className="text-sm px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
                        >
                          Отправить
                        </button>
                        <button
                          onClick={() => { setReportingId(null); setReportComment('') }}
                          className="text-sm px-3 py-1.5 text-gray-500 hover:text-gray-700 transition-colors"
                        >
                          Отмена
                        </button>
                      </div>
                    </div>
                  ) : reportedIds.has(ex.id) ? (
                    <p className="text-xs text-gray-400 flex items-center gap-1">
                      <Flag size={11} /> Ошибка отмечена
                    </p>
                  ) : (
                    <button
                      onClick={() => setReportingId(ex.id)}
                      className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-500 transition-colors"
                    >
                      <Flag size={11} /> Сообщить об ошибке
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Button
        className="w-full mt-2"
        variant="secondary"
        onClick={() => navigate(`/training/session?mode=topic&topic=${slug}`)}
      >
        <Brain size={18} />
        Проверить знания (AI-тест)
      </Button>

      {!completed ? (
        <Button onClick={handleComplete} loading={completing} className="w-full mt-2">
          <CheckCircle size={18} />
          Завершить тему
        </Button>
      ) : (
        <div className="card bg-green-50 border-green-200 text-center">
          <p className="text-green-700 font-semibold">✓ Тема завершена!</p>
          <Button variant="secondary" className="mt-3 mx-auto" onClick={() => navigate('/topics')}>
            К темам
          </Button>
        </div>
      )}
    </div>
  )
}

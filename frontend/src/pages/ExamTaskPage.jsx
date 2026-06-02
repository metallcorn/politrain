import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { examApi } from '../api'
import { useAuthStore, useUIStore } from '../store'
import Button from '../components/ui/Button'
import Spinner from '../components/ui/Spinner'
import { ArrowLeft } from 'lucide-react'

export default function ExamTaskPage() {
  const { type } = useParams()
  const navigate = useNavigate()
  const { user } = useAuthStore()
  const { addToast } = useUIStore()

  const [taskData, setTaskData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [answers, setAnswers] = useState({})
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    examApi.getTask(type)
      .then((r) => setTaskData(r.data))
      .catch(() => addToast('Ошибка загрузки задания', 'error'))
      .finally(() => setLoading(false))
  }, [type])

  const handleSubmit = async () => {
    setSubmitting(true)
    try {
      let payload = {}
      if (type === 'writing') {
        payload = { student_text: text, task_description: taskData.task_description }
      } else if (type === 'reading') {
        payload = {
          answers: taskData.data.questions.map((_, i) => answers[i] || ''),
          questions_data: taskData.data.questions,
        }
      } else if (type === 'grammar') {
        payload = {
          answers: taskData.questions.map((_, i) => answers[i] || ''),
          questions_data: taskData.questions,
        }
      }
      const res = await examApi.submit(type, payload)
      setResult(res.data.result || res.data)
    } catch {
      addToast('Ошибка отправки', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/exam')} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-xl font-bold text-gray-900">
          {type === 'writing' ? 'Письмо' : type === 'reading' ? 'Чтение' : 'Грамматика'}
        </h1>
      </div>

      {taskData?.error && (
        <div className="card bg-red-50 border-red-100">
          <p className="text-red-700">{taskData.error}</p>
        </div>
      )}

      {/* Writing task */}
      {type === 'writing' && taskData && !result && (
        <div className="flex flex-col gap-4">
          <div className="card bg-blue-50 border-blue-100">
            <p className="font-medium text-blue-800 mb-1">Задание:</p>
            <p className="text-gray-700">{taskData.task_description}</p>
          </div>
          <textarea
            className="input resize-none h-48"
            placeholder="Напиши здесь (80-100 слов)..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <p className="text-sm text-gray-400">Слов: {text.trim().split(/\s+/).filter(Boolean).length}</p>
          <Button onClick={handleSubmit} loading={submitting} disabled={text.trim().length < 10}>
            Отправить на проверку
          </Button>
        </div>
      )}

      {/* Reading task */}
      {type === 'reading' && taskData?.data && !result && (
        <div className="flex flex-col gap-4">
          <div className="card">
            <p className="text-sm text-gray-700 whitespace-pre-wrap">{taskData.data.text}</p>
          </div>
          {taskData.data.questions?.map((q, i) => (
            <div key={i} className="card">
              <p className="font-medium text-gray-800 mb-3">{i + 1}. {q.question}</p>
              <div className="flex flex-col gap-2">
                {q.options?.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setAnswers((a) => ({ ...a, [i]: opt }))}
                    className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                      answers[i] === opt ? 'border-primary-800 bg-primary-50 font-medium' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <Button onClick={handleSubmit} loading={submitting}>Проверить</Button>
        </div>
      )}

      {/* Grammar task */}
      {type === 'grammar' && taskData?.questions && !result && (
        <div className="flex flex-col gap-4">
          {taskData.questions.map((q, i) => (
            <div key={i} className="card">
              <p className="font-medium text-gray-800 mb-3">{i + 1}. {q.question}</p>
              <div className="grid grid-cols-2 gap-2">
                {q.options?.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => setAnswers((a) => ({ ...a, [i]: opt }))}
                    className={`text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                      answers[i] === opt ? 'border-primary-800 bg-primary-50 font-medium' : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          ))}
          <Button onClick={handleSubmit} loading={submitting}>Проверить</Button>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className="flex flex-col gap-4">
          <div className="card bg-green-50 border-green-100">
            <h2 className="font-bold text-green-800 text-lg mb-2">Результат</h2>
            {result.scores && (
              <div className="grid grid-cols-2 gap-2 mb-3">
                {Object.entries(result.scores).map(([k, v]) => (
                  <div key={k} className="text-center bg-white rounded-xl p-2">
                    <p className="text-lg font-bold text-primary-800">{v}/5</p>
                    <p className="text-xs text-gray-500">{k}</p>
                  </div>
                ))}
              </div>
            )}
            {result.total !== undefined && !result.scores && (
              <p className="text-2xl font-black text-primary-800">{result.score}%</p>
            )}
            {result.feedback && <p className="text-sm text-gray-700 mt-2">{result.feedback}</p>}
            {result.corrections?.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-gray-700 mb-1">Ошибки:</p>
                <ul className="list-disc list-inside space-y-1">
                  {result.corrections.map((c, i) => <li key={i} className="text-sm text-gray-600">{c}</li>)}
                </ul>
              </div>
            )}
          </div>
          <Button variant="secondary" onClick={() => navigate('/exam')}>К заданиям</Button>
        </div>
      )}
    </div>
  )
}

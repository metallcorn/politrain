import { useEffect, useRef, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { trainingApi } from '../api'
import { useUIStore } from '../store'
import Spinner from '../components/ui/Spinner'
import Button from '../components/ui/Button'
import Flashcard from '../components/training/Flashcard'
import FillBlank from '../components/training/FillBlank'
import MultipleChoice from '../components/training/MultipleChoice'
import TranslatePhrase from '../components/training/TranslatePhrase'
import WordOrder from '../components/training/WordOrder'
import JudgeSentence from '../components/training/JudgeSentence'
import LetterTilesBlank from '../components/training/LetterTilesBlank'
import WordDefinition from '../components/training/WordDefinition'
import ReadingExercise from '../components/training/ReadingExercise'
import SessionResult from '../components/training/SessionResult'
import ProgressBar from '../components/ui/ProgressBar'
import { ArrowLeft, SkipForward, Flag, X, Brain, Sparkles, CheckCircle, Rocket, CalendarDays, BookOpen, MessageCircle } from 'lucide-react'
import Markdown from '../components/ui/Markdown'

export default function TrainingSessionPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { addToast } = useUIStore()
  const mode = params.get('mode') || 'daily'
  const topic = params.get('topic') || null
  const refreshKey = params.get('t') || '0'

  const [exercises, setExercises] = useState([])
  const [current, setCurrent] = useState(0)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [sessionDone, setSessionDone] = useState(false)
  const [stats, setStats] = useState({ correct: 0, total: 0, xp: 0 })
  const [reportOpen, setReportOpen] = useState(false)
  const [reportComment, setReportComment] = useState('')
  const [reportSending, setReportSending] = useState(false)
  const [dailyAlreadyDone, setDailyAlreadyDone] = useState(false)
  const [allVocabDone, setAllVocabDone] = useState(false)
  const [loadProgress, setLoadProgress] = useState(0)
  const [loadStep, setLoadStep] = useState(0)
  const [loadError, setLoadError] = useState(false)
  const [xpFloat, setXpFloat] = useState(null)
  const [aiOpen, setAiOpen] = useState(false)
  const [aiTexts, setAiTexts] = useState({ 1: null, 2: null })
  const [aiLevel, setAiLevel] = useState(1)
  const [aiLoading, setAiLoading] = useState(false)
  const startTimeRef = useRef(null)
  const activeTimeRef = useRef(0)       // accumulated ms while tab was visible
  const lastVisibleRef = useRef(null)   // timestamp when tab became visible
  const lastUserAnswerRef = useRef('')
  const aiNonceRef = useRef(0)          // increments on every exercise transition; guards stale AI fetches

  useEffect(() => {
    const pause = () => {
      if (lastVisibleRef.current) {
        activeTimeRef.current += Date.now() - lastVisibleRef.current
        lastVisibleRef.current = null
      }
    }
    const resume = () => {
      if (lastVisibleRef.current === null && activeTimeRef.current > 0) {
        lastVisibleRef.current = Date.now()
      }
    }
    const onVisibility = () => { document.hidden ? pause() : resume() }
    // window blur/focus catches app-switch on desktop (visibilitychange doesn't fire there)
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('blur', pause)
    window.addEventListener('focus', resume)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('blur', pause)
      window.removeEventListener('focus', resume)
    }
  }, [])

  const GEN_STEPS = [
    'Выбираем темы для тебя...',
    'Генерируем грамматические задания...',
    'Создаём лексические упражнения...',
    'Составляем задания на перевод...',
    'Финальная проверка качества...',
  ]

  useEffect(() => {
    if (!loading) return
    setLoadProgress(0)
    setLoadStep(0)
    const duration = ['daily', 'bonus', 'new', 'topic', 'reading'].includes(mode) ? 55000 : 25000
    const interval = 200
    const step = (interval / duration) * 90
    const stepInterval = duration / GEN_STEPS.length
    let elapsed = 0
    const timer = setInterval(() => {
      elapsed += interval
      setLoadProgress((p) => Math.min(p + step, 90))
      setLoadStep(Math.min(Math.floor(elapsed / stepInterval), GEN_STEPS.length - 1))
    }, interval)
    return () => clearInterval(timer)
  }, [loading, mode])

  const loadSession = () => {
    setLoading(true)
    setLoadError(false)
    trainingApi.session(mode, topic)
      .then((r) => {
        if (r.data.daily_done) { setDailyAlreadyDone(true); return }
        if (r.data.all_vocab_done) { setAllVocabDone(true); return }
        setExercises(r.data.exercises)
        if (r.data.exercises.length === 0) setSessionDone(true)
        else {
          activeTimeRef.current = 0
          lastVisibleRef.current = document.hidden ? null : Date.now()
        }
      })
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    setLoadError(false)
    setSessionDone(false)
    setDailyAlreadyDone(false)
    setAllVocabDone(false)
    setExercises([])
    setCurrent(0)
    setResult(null)
    setStats({ correct: 0, total: 0, xp: 0 })
    loadSession()
  }, [mode, refreshKey])

  const currentEx = exercises[current]

  const handleAnswer = async ({ user_answer, quality, hint_used, autoAdvance }) => {
    if (submitting) return
    setSubmitting(true)
    lastUserAnswerRef.current = user_answer || ''

    try {
      const payload = {
        user_answer,
        exercise_id: currentEx.id || null,
        daily_exercise_id: currentEx.daily_exercise_id || null,
        vocab_id: currentEx.vocab_id || null,
        quality: quality ?? null,
        hint_used: hint_used || false,
      }
      const res = await trainingApi.answer(payload)
      setStats((s) => ({
        correct: s.correct + (res.data.is_correct ? 1 : 0),
        total: s.total + 1,
        xp: s.xp + (res.data.xp_earned || 0),
      }))
      if (res.data.is_correct && res.data.xp_earned > 0) {
        setXpFloat({ id: Date.now(), amount: res.data.xp_earned })
      }
      if (autoAdvance) {
        handleNext()
      } else {
        setResult(res.data)
      }
    } catch (err) {
      addToast('Ошибка проверки ответа', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const resetAiState = () => {
    aiNonceRef.current += 1
    setAiTexts({ 1: null, 2: null })
    setAiLevel(1)
    setAiOpen(false)
  }

  const handleNext = () => {
    setResult(null)
    resetAiState()
    if (current + 1 >= exercises.length) {
      setSessionDone(true)
    } else {
      setCurrent((c) => c + 1)
    }
  }

  const fetchAiLevel = async (level) => {
    if (aiTexts[level] !== null) return
    const nonce = aiNonceRef.current
    setAiLoading(true)
    try {
      const res = await trainingApi.explain({
        exercise_type: currentEx.type,
        question: currentEx.question,
        correct_answer: currentEx.correct_answer,
        user_answer: lastUserAnswerRef.current,
        is_correct: result.is_correct,
        explanation: currentEx.explanation || null,
        translation: currentEx.translation || null,
        level,
      })
      if (aiNonceRef.current !== nonce) return  // navigated away — discard stale response
      setAiTexts((t) => ({ ...t, [level]: res.data.text }))
    } catch {
      if (aiNonceRef.current !== nonce) return
      setAiTexts((t) => ({ ...t, [level]: 'Не удалось получить объяснение — попробуй ещё раз.' }))
    } finally {
      if (aiNonceRef.current === nonce) setAiLoading(false)
    }
  }

  const handleAskAI = () => {
    setAiOpen(true)
    fetchAiLevel(1)
  }

  const handleAskMore = () => {
    setAiLevel(2)
    fetchAiLevel(2)
  }

  const handleSkip = () => {
    // Mark as completed server-side so it doesn't reappear in the next session
    if (currentEx?.daily_exercise_id) {
      trainingApi.answer({
        user_answer: '',
        daily_exercise_id: currentEx.daily_exercise_id,
      }).catch(() => {})
    }
    setResult(null)
    resetAiState()
    if (current + 1 >= exercises.length) {
      setSessionDone(true)
    } else {
      setCurrent((c) => c + 1)
    }
  }

  const handleReportSubmit = async () => {
    setReportSending(true)
    try {
      await trainingApi.report({
        daily_exercise_id: currentEx?.daily_exercise_id || null,
        exercise_id: currentEx?.id || null,
        comment: reportComment || null,
      })
      addToast('Ошибка записана — спасибо!', 'success')
    } catch {
      addToast('Не удалось отправить', 'error')
    } finally {
      setReportSending(false)
      setReportOpen(false)
      setReportComment('')
      // Advance without submitting an answer — report endpoint already marks the exercise
      setResult(null)
      resetAiState()
      if (current + 1 >= exercises.length) {
        setSessionDone(true)
      } else {
        setCurrent((c) => c + 1)
      }
    }
  }

  if (loading) {
    const GenLoader = ({ icon, color, title, subtitle }) => (
      <div className="flex flex-col items-center gap-6 py-12 text-center px-4">
        <div className={`w-20 h-20 rounded-full ${color.bg} flex items-center justify-center`}>
          <span className={color.icon}>{icon}</span>
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">{title}</h2>
          <p className="text-gray-500 text-sm mt-2">{subtitle}</p>
        </div>
        <div className="w-full max-w-xs">
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className={`h-full ${color.bar} rounded-full transition-all duration-200 ease-out`}
              style={{ width: `${loadProgress}%` }} />
          </div>
        </div>
        <p className="text-sm text-gray-400 animate-pulse min-h-5">
          {GEN_STEPS[loadStep]}
        </p>
      </div>
    )

    if (mode === 'bonus') {
      return <GenLoader
        icon={<Brain size={40} className="text-purple-500 animate-pulse" />}
        color={{ bg: 'bg-purple-50', icon: '', bar: 'bg-purple-500' }}
        title="Генерируем задания"
        subtitle="Анализируем ответы, учитываем ошибки — создаём сложнее"
      />
    }
    if (mode === 'daily') {
      return <GenLoader
        icon={<CalendarDays size={40} className="text-primary-600 animate-pulse" />}
        color={{ bg: 'bg-primary-50', icon: '', bar: 'bg-primary-500' }}
        title="Готовим дневные задания"
        subtitle="Собираем персональную подборку на сегодня"
      />
    }
    if (mode === 'new') {
      return <GenLoader
        icon={<Sparkles size={40} className="text-yellow-500 animate-pulse" />}
        color={{ bg: 'bg-yellow-50', icon: '', bar: 'bg-yellow-500' }}
        title="Генерируем новые задания"
        subtitle="Создаём свежие упражнения специально для тебя"
      />
    }
    if (mode === 'topic') {
      return <GenLoader
        icon={<Brain size={40} className="text-indigo-500 animate-pulse" />}
        color={{ bg: 'bg-indigo-50', icon: '', bar: 'bg-indigo-500' }}
        title="Генерируем задания по теме"
        subtitle={topic ? `Тема: ${topic}` : 'Создаём упражнения по выбранной теме'}
      />
    }

    if (mode === 'vocab') {
      return (
        <div className="flex flex-col items-center gap-6 py-12 text-center px-4">
          <div className="w-20 h-20 rounded-full bg-blue-50 flex items-center justify-center">
            <BookOpen size={40} className="text-blue-500 animate-pulse" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">Подбираем слова</h2>
            <p className="text-gray-500 text-sm mt-2">Новые, ошибочные и давно не встречавшиеся</p>
          </div>
          <Spinner />
        </div>
      )
    }
    return <div className="flex justify-center py-12"><Spinner /></div>
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center gap-6 py-12 text-center px-4">
        <div className="w-20 h-20 rounded-full bg-red-50 flex items-center justify-center">
          <X size={40} className="text-red-400" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">Не удалось загрузить задания</h2>
          <p className="text-gray-500 text-sm mt-2">Мистраль не ответил вовремя — попробуй ещё раз</p>
        </div>
        <div className="flex flex-col gap-3 w-full max-w-xs">
          <Button onClick={loadSession}>Попробовать снова</Button>
          <Button variant="secondary" onClick={() => navigate('/training')}>В меню</Button>
        </div>
      </div>
    )
  }

  if (allVocabDone) {
    return (
      <div className="flex flex-col items-center gap-6 py-10 text-center">
        <div className="w-20 h-20 rounded-full bg-blue-50 flex items-center justify-center">
          <CheckCircle size={44} className="text-blue-500" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">Все слова изучены!</h2>
          <p className="text-gray-500 text-sm mt-2">Новые слова появятся позже — или попробуй другой режим</p>
        </div>
        <Button variant="secondary" onClick={() => navigate('/training')}>В меню</Button>
      </div>
    )
  }

  if (dailyAlreadyDone) {
    return (
      <div className="flex flex-col items-center gap-6 py-10 text-center">
        <div className="w-20 h-20 rounded-full bg-green-50 flex items-center justify-center">
          <CheckCircle size={44} className="text-green-500" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-gray-900">Отлично! Дневные задания выполнены</h2>
          <p className="text-gray-500 text-sm mt-2">Возвращайся завтра за новой порцией или продолжи прямо сейчас</p>
        </div>
        <div className="flex flex-col gap-3 w-full">
          <Button onClick={() => navigate(`/training/session?mode=bonus&t=${Date.now()}`)}>
            <Rocket size={18} />
            Ещё задания (бонус)
          </Button>
          <Button variant="secondary" onClick={() => navigate('/training')}>
            В меню
          </Button>
        </div>
      </div>
    )
  }

  if (sessionDone || exercises.length === 0) {
    const accumulated = activeTimeRef.current + (lastVisibleRef.current ? Date.now() - lastVisibleRef.current : 0)
    const sessionDuration = Math.round(accumulated / 1000)
    return (
      <SessionResult
        correct={stats.correct}
        total={stats.total}
        xpEarned={stats.xp}
        streak={0}
        mode={mode}
        topic={topic}
        sessionDuration={sessionDuration}
        exerciseIds={exercises.map(e => e.daily_exercise_id).filter(Boolean)}
      />
    )
  }

  const renderExercise = () => {
    if (!currentEx) return null
    const props = { exercise: currentEx, onAnswer: handleAnswer, result, loading: submitting }

    switch (currentEx.type) {
      case 'flashcard': return <Flashcard {...props} />
      case 'fill_blank': return <FillBlank {...props} />
      case 'multiple_choice': return <MultipleChoice {...props} />
      case 'translate': return <TranslatePhrase {...props} />
      case 'order_words': return <WordOrder {...props} />
      case 'judge_sentence': return <JudgeSentence {...props} />
      case 'letter_tiles': return <LetterTilesBlank {...props} />
      case 'word_definition': return <WordDefinition {...props} />
      case 'reading': return <ReadingExercise {...props} />
      default: return <FillBlank {...props} />
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/training')} className="text-gray-400 hover:text-gray-600 transition-colors">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1">
          <ProgressBar value={current} max={exercises.length} />
        </div>
        <span className="text-sm text-gray-500 flex-shrink-0">{current + 1}/{exercises.length}</span>
      </div>

      <div className="text-xs text-gray-400 uppercase tracking-wide flex items-center gap-1.5">
        <span>
          {currentEx?.source === 'new' ? '✨ Новое'
            : currentEx?.source === 'weak' ? '⚠️ Слабое место'
            : currentEx?.source === 'bonus' ? '🚀 Бонус'
            : currentEx?.source === 'vocab'
              ? currentEx?.vocab_status === 'new' ? '✨ Новое слово'
              : currentEx?.vocab_status === 'error' ? '⚠️ Ошибка'
              : '🔄 Повторение'
            : currentEx?.source === 'topic_d' ? '📖 Тема'
            : currentEx?.source === 'topic' ? '📖 Тема'
            : currentEx?.source === 'review_ai' ? '🔄 Повторение AI'
            : currentEx?.source === 'practice' ? '🔁 Практика'
            : '🔄 Повторение'}
        </span>
        {currentEx?.topic_title && (
          <span className="normal-case text-gray-300">· {currentEx.topic_title}</span>
        )}
      </div>

      <div key={current} className="animate-slide-in">
        <div className={result && !result.is_correct ? 'animate-shake' : undefined}>
          <div className="card relative">
            {result?.is_correct && (
              <div className="absolute inset-0 bg-green-400/30 rounded-2xl pointer-events-none animate-correct-flash z-10" />
            )}
            {renderExercise()}
          </div>
        </div>
      </div>

      {xpFloat && (
        <div
          key={xpFloat.id}
          className="fixed bottom-28 right-5 pointer-events-none z-50 animate-float-up font-bold text-xl text-yellow-500 drop-shadow-md"
          onAnimationEnd={() => setXpFloat(null)}
        >
          +{xpFloat.amount} XP
        </div>
      )}

      {result && (
        <div className="flex flex-col gap-2">
          <Button onClick={handleNext} className="w-full">
            {current + 1 >= exercises.length ? 'Завершить сессию' : 'Следующее →'}
          </Button>
          <button
            onClick={handleAskAI}
            className="flex items-center justify-center gap-1.5 text-sm text-gray-400 hover:text-primary-600 transition-colors py-1"
          >
            <MessageCircle size={14} />
            Объяснить подробнее
          </button>
        </div>
      )}

      <div className="flex items-center justify-between px-1">
        {!result && !submitting ? (
          <button
            onClick={handleSkip}
            className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-600 transition-colors py-1"
          >
            <SkipForward size={13} />
            Пропустить
          </button>
        ) : <span />}
        <button
          onClick={() => setReportOpen(true)}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 transition-colors py-1"
        >
          <Flag size={13} />
          Ошибка в задании
        </button>
      </div>

      {aiOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-end justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 flex flex-col gap-4 max-h-[75vh]">
            <div className="flex items-center justify-between flex-shrink-0">
              <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                <Brain size={18} className="text-primary-600" />
                Объяснение от AI
              </h3>
              <button onClick={() => setAiOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 flex flex-col gap-4">
              {aiLoading && aiTexts[aiLevel] === null ? (
                <div className="flex items-center justify-center gap-2 py-8 text-gray-400">
                  <Brain size={20} className="animate-pulse text-primary-400" />
                  <span className="text-sm">Думаю...</span>
                </div>
              ) : (
                <Markdown className="text-sm text-gray-700 leading-relaxed">{aiTexts[aiLevel]}</Markdown>
              )}

              {/* Level toggle */}
              {aiLevel === 1 && aiTexts[1] !== null && !aiLoading && (
                <button
                  onClick={handleAskMore}
                  className="text-sm text-primary-600 hover:text-primary-800 font-medium transition-colors self-start"
                >
                  Объясни подробнее с примерами →
                </button>
              )}
              {aiLevel === 2 && aiTexts[1] !== null && (
                <button
                  onClick={() => setAiLevel(1)}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors self-start"
                >
                  ← Краткое объяснение
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {reportOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-end justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-gray-900">Сообщить об ошибке</h3>
              <button onClick={() => setReportOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <p className="text-sm text-gray-500">Опишите в чём ошибка — это поможет Мистралю избегать таких заданий в будущем.</p>
            <textarea
              className="input resize-none h-20 text-sm"
              placeholder="Необязательно: неверный ответ, некорректный вопрос, несуществующая форма слова..."
              value={reportComment}
              onChange={(e) => setReportComment(e.target.value)}
              autoFocus
            />
            <div className="flex gap-3">
              <Button
                className="flex-1"
                onClick={handleReportSubmit}
                loading={reportSending}
              >
                Отправить и пропустить
              </Button>
              <button
                onClick={() => setReportOpen(false)}
                className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

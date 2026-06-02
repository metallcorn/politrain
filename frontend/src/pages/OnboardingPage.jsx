import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore, useUIStore } from '../store'
import { onboardingApi, profileApi } from '../api'
import Button from '../components/ui/Button'

const INTEREST_THEMES = [
  { key: 'IT и технологии', emoji: '💻' },
  { key: 'Путешествия', emoji: '✈️' },
  { key: 'Шоппинг и магазины', emoji: '🛍️' },
  { key: 'Рестораны и кафе', emoji: '☕' },
  { key: 'Работа и карьера', emoji: '💼' },
  { key: 'Здоровье и медицина', emoji: '🏥' },
  { key: 'Спорт и активный отдых', emoji: '🏃' },
  { key: 'Банки и финансы', emoji: '🏦' },
  { key: 'Транспорт и ПДД', emoji: '🚗' },
  { key: 'Культура и история', emoji: '🎭' },
  { key: 'Дом и быт', emoji: '🏠' },
  { key: 'Семья и отношения', emoji: '👨‍👩‍👧' },
]

export default function OnboardingPage() {
  const [step, setStep] = useState(1)
  const [lang, setLang] = useState('ru')
  const [questions, setQuestions] = useState([])
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)
  const [selectedThemes, setSelectedThemes] = useState([])
  const [loading, setLoading] = useState(false)
  const { fetchMe } = useAuthStore()
  const { addToast } = useUIStore()
  const navigate = useNavigate()

  const handleLangSelect = async () => {
    try {
      await onboardingApi.saveSettings({ native_language: lang, target_language: 'pl' })
      setStep(2)
    } catch {
      addToast('Ошибка сохранения настроек', 'error')
    }
  }

  const handleStartTest = async () => {
    setLoading(true)
    try {
      const res = await onboardingApi.getTest()
      setQuestions(res.data.questions)
      setStep(3)
    } catch {
      addToast('Ошибка загрузки теста', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSubmitTest = async () => {
    setLoading(true)
    try {
      const answersList = Object.entries(answers).map(([id, answer]) => ({
        question_id: parseInt(id),
        answer,
      }))
      const res = await onboardingApi.submitTest({ answers: answersList })
      setResult(res.data)
      setStep(4)
    } catch {
      addToast('Ошибка отправки ответов', 'error')
    } finally {
      setLoading(false)
    }
  }

  const toggleTheme = (key) => {
    setSelectedThemes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  const handleSaveThemes = async () => {
    setLoading(true)
    try {
      await profileApi.updatePreferences({
        conversational_weight: 0.25,
        idiom_weight: 0.25,
        situational_weight: 0.25,
        grammar_weight: 0.25,
        session_length: 'standard',
        daily_goal_minutes: 15,
        interest_themes: selectedThemes,
      })
    } catch {
      // non-critical, continue
    } finally {
      setLoading(false)
    }
    await fetchMe()
    navigate('/dashboard')
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-white p-4">
      <div className="w-full max-w-lg">
        {/* Step 1: Language */}
        {step === 1 && (
          <div className="card flex flex-col gap-6">
            <div className="text-center">
              <div className="w-16 h-16 bg-primary-800 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <span className="text-white font-bold text-2xl">P</span>
              </div>
              <h1 className="text-2xl font-bold">Добро пожаловать!</h1>
              <p className="text-gray-500 mt-1">Выбери язык интерфейса</p>
            </div>
            <div className="flex gap-4">
              {[{ value: 'ru', label: '🇷🇺 Русский' }, { value: 'en', label: '🇬🇧 English' }].map((l) => (
                <button
                  key={l.value}
                  onClick={() => setLang(l.value)}
                  className={`flex-1 py-4 rounded-xl border-2 font-semibold transition-all ${
                    lang === l.value
                      ? 'border-primary-800 bg-primary-50 text-primary-800'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {l.label}
                </button>
              ))}
            </div>
            <Button onClick={handleLangSelect} className="w-full">
              Далее →
            </Button>
          </div>
        )}

        {/* Step 2: Intro */}
        {step === 2 && (
          <div className="card flex flex-col gap-6 text-center">
            <div>
              <p className="text-4xl mb-3">🇵🇱</p>
              <h2 className="text-xl font-bold">Изучаем польский</h2>
              <p className="text-gray-500 mt-2">
                Пройди короткий тест (10 вопросов) чтобы мы определили твой уровень
              </p>
            </div>
            <div className="text-left bg-primary-50 rounded-xl p-4 flex flex-col gap-2">
              <p className="text-sm font-medium text-primary-800">Что тебя ждёт:</p>
              {['10 вопросов на 5-10 минут', 'Определение уровня A0-B1', 'Персональный план обучения'].map((i) => (
                <p key={i} className="text-sm text-gray-600">✓ {i}</p>
              ))}
            </div>
            <Button onClick={handleStartTest} loading={loading} className="w-full">
              Начать тест
            </Button>
          </div>
        )}

        {/* Step 3: Test */}
        {step === 3 && (
          <div className="card flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold">Тест на уровень</h2>
              <span className="text-sm text-gray-500">{Object.keys(answers).length}/{questions.length}</span>
            </div>
            <div className="flex flex-col gap-4 max-h-96 overflow-y-auto pr-1">
              {questions.map((q, i) => (
                <div key={q.id} className="border border-gray-100 rounded-xl p-4">
                  <p className="text-sm font-medium text-gray-800 mb-3">{i + 1}. {q.question}</p>
                  <div className="grid grid-cols-2 gap-2">
                    {q.options?.map((opt) => (
                      <button
                        key={opt}
                        onClick={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                        className={`text-left text-sm px-3 py-2 rounded-lg border transition-colors ${
                          answers[q.id] === opt
                            ? 'border-primary-800 bg-primary-50 text-primary-800 font-medium'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <Button
              onClick={handleSubmitTest}
              loading={loading}
              disabled={Object.keys(answers).length < questions.length}
              className="w-full"
            >
              Завершить тест
            </Button>
          </div>
        )}

        {/* Step 4: Result */}
        {step === 4 && result && (
          <div className="card flex flex-col gap-6 text-center">
            <div>
              <p className="text-5xl font-black text-primary-800 mb-2">{result.level}</p>
              <h2 className="text-xl font-bold">Твой уровень</h2>
              <p className="text-gray-500 mt-2">{result.message}</p>
              <p className="text-sm text-gray-400 mt-1">
                {result.correct_count} из {result.total} правильных ответов
              </p>
            </div>
            <Button onClick={() => setStep(5)} className="w-full">
              Далее →
            </Button>
          </div>
        )}

        {/* Step 5: Interest themes */}
        {step === 5 && (
          <div className="card flex flex-col gap-5">
            <div className="text-center">
              <p className="text-3xl mb-2">🎯</p>
              <h2 className="text-xl font-bold">Что тебе интересно?</h2>
              <p className="text-gray-500 text-sm mt-1">
                Выбери темы — задания будут строиться вокруг них
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {INTEREST_THEMES.map((t) => (
                <button
                  key={t.key}
                  onClick={() => toggleTheme(t.key)}
                  className={`flex items-center gap-2 px-3 py-3 rounded-xl border-2 text-sm font-medium text-left transition-all ${
                    selectedThemes.includes(t.key)
                      ? 'border-primary-800 bg-primary-50 text-primary-800'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  <span className="text-lg flex-shrink-0">{t.emoji}</span>
                  <span className="leading-tight">{t.key}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-400 text-center">
              {selectedThemes.length === 0
                ? 'Можно пропустить — будут разные темы'
                : `Выбрано: ${selectedThemes.length}`}
            </p>
            <Button onClick={handleSaveThemes} loading={loading} className="w-full">
              {selectedThemes.length === 0 ? 'Пропустить' : 'Начать обучение 🚀'}
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}

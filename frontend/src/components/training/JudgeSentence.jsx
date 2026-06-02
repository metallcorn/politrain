import { useState } from 'react'
import Button from '../ui/Button'
import { CheckCircle, XCircle } from 'lucide-react'
import Markdown from '../ui/Markdown'

export default function JudgeSentence({ exercise, onAnswer, result, loading }) {
  const [chosen, setChosen] = useState(null)
  const [translationShown, setTranslationShown] = useState(false)
  const [hintUsed, setHintUsed] = useState(false)

  const handleChoice = (value) => {
    if (result || loading) return
    setChosen(value)
    onAnswer({ user_answer: value, hint_used: hintUsed })
  }

  const btnClass = (value) => {
    const base = 'flex-1 flex flex-col items-center gap-2 py-5 rounded-2xl border-2 font-semibold text-base transition-all'
    if (!result && chosen === value) return `${base} border-primary-400 bg-primary-50 text-primary-800`
    if (!result) return `${base} border-gray-200 bg-white text-gray-700 hover:border-primary-300 hover:bg-primary-50`
    const isCorrect = result.correct_answer === value
    const isChosen = chosen === value
    if (isChosen && result.is_correct) return `${base} border-green-400 bg-green-50 text-green-700`
    if (isChosen && !result.is_correct) return `${base} border-red-400 bg-red-50 text-red-700`
    if (!isChosen && isCorrect) return `${base} border-green-400 bg-green-50 text-green-700`
    return `${base} border-gray-100 bg-gray-50 text-gray-400`
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">Это правильное предложение?</p>
        <p className="text-xl font-semibold text-gray-900 leading-relaxed">{exercise.question}</p>
        {exercise.translation && !result && (
          translationShown
            ? <p className="text-sm text-amber-600 mt-2 italic animate-fade-in">"{exercise.translation}" <span className="text-xs opacity-60">(-1 XP)</span></p>
            : <button
                onClick={() => { setTranslationShown(true); setHintUsed(true) }}
                className="text-xs text-gray-400 hover:text-amber-500 transition-colors mt-2 flex items-center gap-1"
              >
                💡 Показать перевод <span className="opacity-60">(-1 XP)</span>
              </button>
        )}
        {exercise.translation && result && (
          <p className="text-sm text-gray-500 mt-2 italic">"{exercise.translation}"</p>
        )}
      </div>

      <div className="flex gap-3">
        <button className={btnClass('true')} onClick={() => handleChoice('true')} disabled={!!result || loading}>
          <CheckCircle size={28} className={result?.correct_answer === 'true' ? 'text-green-500' : chosen === 'true' ? 'text-primary-600' : 'text-gray-400'} />
          Правильное
        </button>
        <button className={btnClass('false')} onClick={() => handleChoice('false')} disabled={!!result || loading}>
          <XCircle size={28} className={result?.correct_answer === 'false' ? 'text-green-500' : chosen === 'false' ? 'text-primary-600' : 'text-gray-400'} />
          Неправильное
        </button>
      </div>

      {result && (
        <div className={`rounded-xl p-4 animate-bounce-in ${result.is_correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <p className={`font-semibold mb-1 ${result.is_correct ? 'text-green-700' : 'text-red-700'}`}>
            {result.is_correct ? '✓ Верно!' : '✗ Неверно'}
          </p>
          {result.explanation && <Markdown className="text-sm text-gray-700">{result.explanation}</Markdown>}
        </div>
      )}
    </div>
  )
}

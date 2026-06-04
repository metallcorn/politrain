import { useState, useMemo } from 'react'
import Button from '../ui/Button'
import Markdown from '../ui/Markdown'
import WordHintText from './WordHintText'

function normalize(s) {
  return (s || '').toLowerCase().trim()
    .replace(/ё/g, 'е')
    .replace(/[.,!?;:]/g, '')
}

export default function LetterTilesBlank({ exercise, onAnswer, result, loading }) {
  const tiles = useMemo(() => {
    const arr = [...exercise.correct_answer.toLowerCase()]
      .map((letter, i) => ({ id: i, letter }))
    // Fisher-Yates shuffle, retry until at least one tile is out of original position
    for (let attempt = 0; attempt < 5; attempt++) {
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]]
      }
      if (arr.length <= 1 || arr.some((t, i) => t.id !== i)) break
    }
    return arr
  }, [exercise.correct_answer])

  const [available, setAvailable] = useState(tiles)
  const [arranged, setArranged] = useState([])
  const [submitted, setSubmitted] = useState(false)
  const [hintShown, setHintShown] = useState(false)
  const [hintUsed, setHintUsed] = useState(false)

  const wordHints = exercise.word_hints || {}
  const hasHints = Object.keys(wordHints).length > 0

  const place = (tile) => {
    if (submitted) return
    setAvailable(a => a.filter(t => t.id !== tile.id))
    setArranged(a => [...a, tile])
  }

  const unplace = (tile) => {
    if (submitted) return
    setArranged(a => a.filter(t => t.id !== tile.id))
    setAvailable(a => [...a, tile])
  }

  const handleSubmit = () => {
    if (submitted || loading) return
    setSubmitted(true)
    const userAnswer = arranged.map(t => t.letter).join('')
    onAnswer({ user_answer: userAnswer, hint_used: hintUsed })
  }

  const handleDontKnow = () => {
    if (submitted || loading) return
    setSubmitted(true)
    onAnswer({ user_answer: '', hint_used: hintUsed })
  }

  const tileBase = 'w-11 h-11 rounded-xl text-base font-bold border-2 transition-all active:scale-95 flex items-center justify-center'

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        <WordHintText
          text={exercise.question}
          wordHints={wordHints}
          onHintUsed={() => setHintUsed(true)}
          saveToVocab
          className="text-lg font-medium text-gray-800"
        />
        {exercise.translation && (
          <p className="text-sm text-gray-400 mt-1 italic">{exercise.translation}</p>
        )}
        {hasHints && !submitted && (
          <p className="text-xs text-gray-400 mt-1">Нажми на подчёркнутое слово — увидишь перевод</p>
        )}
        {exercise.hint && !submitted && (
          hintShown
            ? <div className="text-sm text-amber-600 mt-2 animate-fade-in">💡 <Markdown className="inline">{exercise.hint}</Markdown> <span className="text-xs opacity-60">(-1 XP)</span></div>
            : <button
                onClick={() => { setHintShown(true); setHintUsed(true) }}
                className="text-xs text-gray-400 hover:text-amber-500 transition-colors mt-2 flex items-center gap-1"
              >
                💡 Показать подсказку <span className="opacity-60">(-1 XP)</span>
              </button>
        )}
      </div>

      {/* Answer zone — fixed min-height so button doesn't jump */}
      <div className="min-h-16 border-2 border-dashed border-primary-200 rounded-xl p-3 flex flex-wrap gap-2 content-start bg-primary-50/40">
        {arranged.length === 0
          ? <p className="text-gray-400 text-sm self-center">Выбирай буквы снизу...</p>
          : arranged.map(tile => (
              <button
                key={tile.id}
                onClick={() => unplace(tile)}
                disabled={submitted}
                className={`${tileBase} bg-primary-800 text-white border-primary-700 hover:bg-primary-700 disabled:opacity-70`}
              >
                {tile.letter}
              </button>
            ))
        }
      </div>

      {/* Available letters — fixed min-height so layout doesn't collapse */}
      <div className="min-h-16 flex flex-wrap gap-2 justify-center content-start">
        {available.map(tile => (
          <button
            key={tile.id}
            onClick={() => place(tile)}
            disabled={submitted}
            className={`${tileBase} bg-white border-gray-200 text-gray-800 hover:border-primary-400 hover:bg-primary-50 disabled:opacity-40`}
          >
            {tile.letter}
          </button>
        ))}
      </div>

      {!submitted && (
        <div className="sticky bottom-4 flex gap-2">
          <Button variant="secondary" className="flex-1" onClick={handleDontKnow} disabled={loading}>
            Не знаю
          </Button>
          <Button
            className="flex-1"
            onClick={handleSubmit}
            disabled={available.length > 0 || loading}
          >
            Проверить
          </Button>
        </div>
      )}

      {result && (
        <div className={`rounded-xl p-4 animate-bounce-in ${result.is_correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <p className={`font-semibold ${result.is_correct ? 'text-green-700' : 'text-red-700'}`}>
            {result.is_correct ? '✓ Правильно!' : '✗ Неправильно'}
            {hintUsed && result.is_correct && <span className="font-normal text-sm ml-2">(с подсказкой)</span>}
          </p>
          {!result.is_correct && (
            <p className="text-sm text-gray-700 mt-1">Правильно: <strong>{result.correct_answer}</strong></p>
          )}
          {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
          {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
        </div>
      )}
    </div>
  )
}

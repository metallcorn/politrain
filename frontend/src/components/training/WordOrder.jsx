import { useState } from 'react'
import Button from '../ui/Button'
import ExerciseResult from './ExerciseResult'

export default function WordOrder({ exercise, onAnswer, result }) {
  // Support both "[word1, word2]" format and "word1 / word2 / word3" format
  const bracketMatch = exercise.question.match(/\[([^\]]+)\]/)
  const words = bracketMatch
    ? bracketMatch[1].split(/[,/]+/).map((w) => w.trim()).filter(Boolean)
    : exercise.question.split('/').map((w) => w.replace(/\(.*?\)/g, '').replace(/[?.!]$/,'').trim()).filter(Boolean)
  const [arranged, setArranged] = useState([])
  const [available, setAvailable] = useState([...words].sort(() => Math.random() - 0.5))
  const [submitted, setSubmitted] = useState(false)

  const addWord = (word, idx) => {
    if (submitted) return
    setArranged((a) => [...a, word])
    setAvailable((a) => a.filter((_, i) => i !== idx))
  }

  const removeWord = (word, idx) => {
    if (submitted) return
    setAvailable((a) => [...a, word])
    setArranged((a) => a.filter((_, i) => i !== idx))
  }

  const handleSubmit = () => {
    if (arranged.length === 0) return
    setSubmitted(true)
    onAnswer({ user_answer: arranged.join(' ') })
  }

  const hintMatch = exercise.question.match(/\(([^)]+)\)/)
  const questionText = bracketMatch
    ? exercise.question.replace(/\[.*?\]/, '').trim()
    : (hintMatch?.[1] || exercise.hint || 'Составь предложение из слов:')

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        <p className="text-sm text-gray-500 mb-1">{questionText}</p>
      </div>

      {/* Answer zone — fixed min-height so button doesn't jump */}
      <div className="min-h-24 border-2 border-dashed border-gray-200 rounded-xl p-3 flex flex-wrap gap-2 content-start bg-gray-50">
        {arranged.length === 0 && <p className="text-gray-400 text-sm self-center">Нажимай слова снизу...</p>}
        {arranged.map((word, i) => (
          <button
            key={i}
            onClick={() => removeWord(word, i)}
            className="px-5 py-3 bg-primary-800 text-white rounded-xl text-base font-medium hover:bg-primary-700 active:scale-95 transition-all"
          >
            {word}
          </button>
        ))}
      </div>

      {/* Available words — fixed min-height so layout doesn't collapse as words are picked */}
      <div className="min-h-24 flex flex-wrap gap-2 content-start">
        {available.map((word, i) => (
          <button
            key={i}
            onClick={() => addWord(word, i)}
            disabled={submitted}
            className="px-5 py-3 bg-white border-2 border-gray-200 rounded-xl text-base font-medium hover:border-primary-400 hover:bg-primary-50 active:scale-95 transition-all disabled:opacity-50"
          >
            {word}
          </button>
        ))}
      </div>

      {!submitted && (
        <div className="sticky bottom-4">
          <Button onClick={handleSubmit} disabled={arranged.length === 0}>
            Проверить
          </Button>
        </div>
      )}

      <ExerciseResult
        result={result}
        variants={result && !result.is_correct && result.correct_answer
          ? result.correct_answer.split(' / ').map(s => s.trim()).filter(Boolean)
          : null}
        translation={exercise.translation}
      />
    </div>
  )
}

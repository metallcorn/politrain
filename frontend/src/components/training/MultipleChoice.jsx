import { useState } from 'react'
import WordHintText from './WordHintText'
import HintButton from './HintButton'
import ExerciseResult from './ExerciseResult'

export default function MultipleChoice({ exercise, onAnswer, result }) {
  const [selected, setSelected] = useState(null)
  const [hintUsed, setHintUsed] = useState(false)

  const handleSelect = (option) => {
    if (selected) return
    setSelected(option)
    onAnswer({ user_answer: option, hint_used: hintUsed })
  }

  const options = exercise.options || []
  const wordHints = exercise.word_hints || {}
  const hasHints = Object.keys(wordHints).length > 0

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
        {!selected && <HintButton hint={exercise.hint} onReveal={() => setHintUsed(true)} />}
        {!selected && (
          <p className="text-xs text-gray-400 mt-2">Нажми на любое слово — покажу перевод (−1 XP)</p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2">
        {options.map((option) => {
          const norm = (s) => s?.trim().toLowerCase()
          const serverCorrect = result?.correct_answer
          const isCorrectOption = selected
            ? norm(option) === norm(exercise.correct_answer) || (serverCorrect && norm(option) === norm(serverCorrect))
            : false

          let cls = 'w-full text-left p-3 rounded-xl border font-medium transition-all '
          if (!selected) {
            cls += 'border-gray-200 hover:border-primary-400 hover:bg-primary-50 cursor-pointer'
          } else if (isCorrectOption) {
            cls += 'border-green-500 bg-green-50 text-green-700'
          } else if (option === selected) {
            cls += 'border-red-400 bg-red-50 text-red-700'
          } else {
            cls += 'border-gray-200 text-gray-400'
          }

          return (
            <button key={option} className={cls} onClick={() => handleSelect(option)}>
              {option}
            </button>
          )
        })}
      </div>

      <ExerciseResult
        result={result}
        hintUsed={hintUsed}
        showCorrectAnswer={!!result && !options.some(o => o.trim().toLowerCase() === (result.correct_answer || '').trim().toLowerCase())}
      />
    </div>
  )
}

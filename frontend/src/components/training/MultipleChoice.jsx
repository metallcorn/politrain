import { useState } from 'react'
import Markdown from '../ui/Markdown'
import WordHintText from './WordHintText'

export default function MultipleChoice({ exercise, onAnswer, result }) {
  const [selected, setSelected] = useState(null)
  const [hintUsed, setHintUsed] = useState(false)
  const [hintShown, setHintShown] = useState(false)

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
        {exercise.hint && !selected && (
          hintShown
            ? <div className="text-sm text-amber-600 mt-2 animate-fade-in">💡 <Markdown className="inline">{exercise.hint}</Markdown> <span className="text-xs opacity-60">(-1 XP)</span></div>
            : <button
                onClick={() => { setHintShown(true); setHintUsed(true) }}
                className="text-xs text-gray-400 hover:text-amber-500 transition-colors mt-2 flex items-center gap-1"
              >
                💡 Показать подсказку <span className="opacity-60">(-1 XP)</span>
              </button>
        )}
        {hasHints && !selected && (
          <p className="text-xs text-gray-400 mt-2">Нажми на подчёркнутое слово — увидишь перевод</p>
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

      {result && (
        <div className={`rounded-xl p-4 animate-bounce-in ${result.is_correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <p className={`font-semibold ${result.is_correct ? 'text-green-700' : 'text-red-700'}`}>
            {result.is_correct ? '✓ Правильно!' : '✗ Неправильно'}
          </p>
          {!result.is_correct && result.correct_answer && !options.some(o => o.trim().toLowerCase() === result.correct_answer.trim().toLowerCase()) && (
            <p className="text-sm text-gray-700 mt-1">Правильно: <strong>{result.correct_answer}</strong></p>
          )}
          {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
          {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
        </div>
      )}
    </div>
  )
}

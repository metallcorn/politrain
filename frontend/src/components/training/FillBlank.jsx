import { useState, useRef } from 'react'
import Input from '../ui/Input'
import Button from '../ui/Button'
import PolishKeyboard from './PolishKeyboard'
import WordHintText from './WordHintText'
import Markdown from '../ui/Markdown'

export default function FillBlank({ exercise, onAnswer, result, loading }) {
  const [value, setValue] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [hintUsed, setHintUsed] = useState(false)
  const [hintShown, setHintShown] = useState(false)
  const inputRef = useRef(null)

  const handleSubmit = () => {
    if (!value.trim()) return
    setSubmitted(true)
    onAnswer({ user_answer: value.trim(), hint_used: hintUsed })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !submitted) handleSubmit()
  }

  const wordHints = exercise.word_hints || {}
  const hasHints = Object.keys(wordHints).length > 0

  // For fill_blank, show the question as plain text (with ___ as-is),
  // but make surrounding words clickable for context hints.
  // Split on ___ to keep the blank visually clear.
  const parts = exercise.question.split('___')

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        {hasHints ? (
          <div className="text-lg font-medium text-gray-800 mb-1 leading-relaxed">
            {parts.map((part, i) => (
              <span key={i}>
                <WordHintText
                  text={part}
                  wordHints={wordHints}
                  onHintUsed={() => setHintUsed(true)}
                  className="inline"
                />
                {i < parts.length - 1 && (
                  <span className="inline-block mx-1 px-2 py-0.5 border-b-2 border-primary-500 text-primary-600 font-bold">___</span>
                )}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-lg font-medium text-gray-800 mb-1">{exercise.question}</p>
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
        {exercise.translation && <p className="text-sm text-gray-500 mt-1 italic">{exercise.translation}</p>}
        {hasHints && !submitted && (
          <p className="text-xs text-gray-400 mt-2">Нажми на слово — увидишь перевод{hintUsed ? ' (−1 XP)' : ' (−1 XP за использование)'}</p>
        )}
      </div>

      <Input
        ref={inputRef}
        placeholder="Твой ответ..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={submitted}
        autoFocus
      />

      {!submitted && (
        <>
          <PolishKeyboard inputRef={inputRef} value={value} onChange={setValue} />
          <Button onClick={handleSubmit} disabled={!value.trim()}>
            Проверить
          </Button>
        </>
      )}

      {result && (
        <div className={`rounded-xl p-4 animate-bounce-in ${result.is_correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
          <p className={`font-semibold ${result.is_correct ? 'text-green-700' : 'text-red-700'}`}>
            {result.is_correct
              ? result.diacritic_hint ? '✓ Верно, но...' : '✓ Правильно!'
              : '✗ Неправильно'}
            {hintUsed && result.is_correct && <span className="font-normal text-sm ml-2">(с подсказкой)</span>}
          </p>
          {result.diacritic_hint && (
            <p className="text-sm text-amber-700 mt-1">
              Не забывайте про диакритические знаки: <strong>{result.correct_answer}</strong>
            </p>
          )}
          {!result.is_correct && (
            <p className="text-sm text-gray-700 mt-1">Правильный ответ: <strong>{result.correct_answer}</strong></p>
          )}
          {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
          {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
        </div>
      )}
    </div>
  )
}

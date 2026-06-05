import { useState, useRef } from 'react'
import Input from '../ui/Input'
import Button from '../ui/Button'
import PolishKeyboard from './PolishKeyboard'
import Markdown from '../ui/Markdown'
import WordHintText from './WordHintText'

export default function WordDefinition({ exercise, onAnswer, result, loading }) {
  const [value, setValue] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [hintShown, setHintShown] = useState(false)
  const [hintUsed, setHintUsed] = useState(false)
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

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Угадай слово</p>
        <WordHintText
          text={exercise.question}
          wordHints={wordHints}
          onHintUsed={() => setHintUsed(true)}
          saveToVocab
          className="text-lg font-medium text-gray-800 leading-relaxed"
        />
        {hasHints && !submitted && (
          <p className="text-xs text-gray-400 mt-2">Подчёркнутые слова — нажми для перевода</p>
        )}
        {exercise.hint && !submitted && (
          hintShown
            ? <div className="text-sm text-amber-600 mt-3 animate-fade-in">
                💡 {exercise.hint} <span className="text-xs opacity-60">(-1 XP)</span>
              </div>
            : <button
                onClick={() => { setHintShown(true); setHintUsed(true) }}
                className="text-xs text-gray-400 hover:text-amber-500 transition-colors mt-3 flex items-center gap-1"
              >
                💡 Показать подсказку <span className="opacity-60">(-1 XP)</span>
              </button>
        )}
      </div>

      <Input
        ref={inputRef}
        placeholder="Польское слово..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={submitted}
        autoFocus
      />

      {!submitted && (
        <>
          <PolishKeyboard inputRef={inputRef} value={value} onChange={setValue} />
          <Button onClick={handleSubmit} disabled={!value.trim() || loading}>
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
          {exercise.translation && (
            <p className="text-sm text-gray-500 mt-1 italic">{exercise.translation}</p>
          )}
          {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
          {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
        </div>
      )}
    </div>
  )
}

import { useState, useRef } from 'react'
import Input from '../ui/Input'
import Button from '../ui/Button'
import PolishKeyboard from './PolishKeyboard'
import WordHintText from './WordHintText'
import HintButton from './HintButton'
import ExerciseResult from './ExerciseResult'

export default function FillBlank({ exercise, onAnswer, result, loading }) {
  const [value, setValue] = useState('')
  const [submitted, setSubmitted] = useState(false)
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
                  saveToVocab
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
        {!submitted && <HintButton hint={exercise.hint} onReveal={() => setHintUsed(true)} />}
        {exercise.translation && <p className="text-sm text-gray-500 mt-1 italic">{exercise.translation}</p>}
        {hasHints && !submitted && (
          <p className="text-xs text-gray-400 mt-2">Подчёркнутые слова — нажми для перевода{hintUsed ? ' (−1 XP)' : ' (−1 XP)'}</p>
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

      <ExerciseResult result={result} hintUsed={hintUsed} userAnswer={value} />
    </div>
  )
}

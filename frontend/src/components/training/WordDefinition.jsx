import { useState, useRef } from 'react'
import Input from '../ui/Input'
import Button from '../ui/Button'
import PolishKeyboard from './PolishKeyboard'
import WordHintText from './WordHintText'
import HintButton from './HintButton'
import ExerciseResult from './ExerciseResult'

export default function WordDefinition({ exercise, onAnswer, result, loading }) {
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
        {!submitted && <HintButton hint={exercise.hint} onReveal={() => setHintUsed(true)} />}
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

      <ExerciseResult result={result} hintUsed={hintUsed} translation={exercise.translation} userAnswer={value} />
    </div>
  )
}

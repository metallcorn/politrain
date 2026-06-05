import { useState, useRef } from 'react'
import Button from '../ui/Button'
import PolishKeyboard from './PolishKeyboard'
import WordHintText from './WordHintText'
import Markdown from '../ui/Markdown'

export default function TranslatePhrase({ exercise, onAnswer, result, loading }) {
  const [value, setValue] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [hintUsed, setHintUsed] = useState(false)
  const textareaRef = useRef(null)

  const handleSubmit = () => {
    if (!value.trim()) return
    setSubmitted(true)
    onAnswer({ user_answer: value.trim(), hint_used: hintUsed })
  }

  const wordHints = exercise.word_hints || {}
  const hasHints = Object.keys(wordHints).length > 0

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Переведи на польский:</p>
        <WordHintText
          text={exercise.question}
          wordHints={wordHints}
          onHintUsed={() => setHintUsed(true)}
          className="text-xl font-semibold text-gray-800 leading-relaxed"
        />
        {hasHints && !submitted && (
          <p className="text-xs text-gray-400 mt-2">Подчёркнутые слова — нажми для перевода (−1 XP)</p>
        )}
      </div>

      <textarea
        ref={textareaRef}
        className="input resize-none h-24"
        placeholder="Твой перевод..."
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={submitted || loading}
        autoFocus
      />

      {!submitted && (
        <>
          <PolishKeyboard inputRef={textareaRef} value={value} onChange={setValue} />
          <Button onClick={handleSubmit} loading={loading} disabled={!value.trim()}>
            Проверить
          </Button>
        </>
      )}

      {submitted && loading && (
        <div className="flex items-center gap-2 text-sm text-gray-500 animate-pulse py-2">
          <div className="w-4 h-4 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin" />
          Проверяем ответ...
        </div>
      )}

      {result && (
        <div className={`rounded-xl p-4 animate-bounce-in ${
          result.is_correct
            ? result.diacritic_hint ? 'bg-amber-50 border border-amber-200' : 'bg-green-50 border border-green-200'
            : 'bg-orange-50 border border-orange-200'
        }`}>
          <p className={`font-semibold ${
            result.is_correct
              ? result.diacritic_hint ? 'text-amber-700' : 'text-green-700'
              : 'text-orange-700'
          }`}>
            {result.is_correct
              ? result.diacritic_hint ? '✓ Верно, но обратите внимание на написание' : '✓ Правильно!'
              : '~ Почти верно'}
            {hintUsed && result.is_correct && <span className="font-normal text-sm ml-2">(с подсказкой)</span>}
          </p>
          {result.diacritic_hint && (
            <p className="text-sm text-amber-700 mt-1">
              Не забывайте про диакритические знаки: <strong>{result.correct_answer}</strong>
            </p>
          )}
          {!result.diacritic_hint && (
            <p className="text-sm text-gray-700 mt-1">Образцовый ответ: <strong>{result.correct_answer}</strong></p>
          )}
          {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
          {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
        </div>
      )}
    </div>
  )
}

import { useState, useMemo, useRef, useEffect } from 'react'
import Button from '../ui/Button'

function normalize(str) {
  return (str || '')
    .toLowerCase()
    .trim()
    .replace(/ё/g, 'е')
    .replace(/[.,!?;:«»"'()[\]]/g, '')
    .replace(/-/g, ' ')
    .replace(/\s+/g, ' ')
}

function isClose(userInput, expected) {
  const u = normalize(userInput)
  if (!u) return false
  const alternatives = (expected || '').split(' / ').map(normalize)
  return alternatives.some(c => {
    if (u === c) return true
    if (c.includes(u) && u.length >= 4) return true
    return false
  })
}

// Vocab cards: type-and-check with fuzzy matching
function VocabCard({ exercise, onAnswer, result, loading }) {
  const reverse = useMemo(
    () => Math.random() < 0.5,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [exercise.id ?? exercise.question]
  )

  const shownWord = reverse ? exercise.correct_answer : exercise.question
  const expectedAnswer = reverse ? exercise.question : exercise.correct_answer
  const shownLabel = reverse ? 'Русский' : 'Польский'
  const inputPlaceholder = reverse ? 'Напиши по-польски...' : 'Напиши перевод...'

  const [inputValue, setInputValue] = useState('')
  const [checked, setChecked] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => {
    setInputValue('')
    setChecked(null)
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [exercise.id ?? exercise.question])

  const handleSubmit = () => {
    if (!inputValue.trim() || checked || loading) return
    const correct = isClose(inputValue, expectedAnswer)
    setChecked({ correct, typed: inputValue })
    onAnswer({ user_answer: inputValue, quality: correct ? 5 : 0 })
  }

  const handleDontKnow = () => {
    if (checked || loading) return
    setChecked({ correct: false, typed: '' })
    onAnswer({ user_answer: '', quality: 0 })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !checked && !loading) handleSubmit()
  }

  return (
    <div className="flex flex-col items-center gap-6">
      <div
        className="w-full bg-white rounded-2xl border-2 border-primary-100 flex flex-col items-center justify-center p-8"
        style={{ minHeight: 180 }}
      >
        <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">{shownLabel}</p>
        <p className="text-3xl font-bold text-primary-800 text-center">{shownWord}</p>
      </div>

      {!checked && (
        <div className="w-full flex flex-col gap-3">
          <input
            ref={inputRef}
            type="text"
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={inputPlaceholder}
            disabled={loading}
            className="w-full border-2 border-gray-200 rounded-xl px-4 py-3 text-lg focus:outline-none focus:border-primary-400 disabled:opacity-50"
          />
          <div className="flex gap-2">
            <Button variant="secondary" className="flex-1" onClick={handleDontKnow} disabled={loading}>
              Не знаю
            </Button>
            <Button className="flex-1" onClick={handleSubmit} disabled={!inputValue.trim() || loading}>
              Проверить
            </Button>
          </div>
        </div>
      )}

      {checked && (
        <div className={`w-full rounded-xl p-4 text-center animate-bounce-in ${checked.correct ? 'bg-green-50 border-2 border-green-200' : 'bg-red-50 border-2 border-red-200'}`}>
          <p className={`text-lg font-semibold ${checked.correct ? 'text-green-700' : 'text-red-700'}`}>
            {checked.correct ? '✓ Верно!' : '✗ Неверно'}
            {checked.correct && result?.xp_earned > 0 && (
              <span className="text-xs font-normal text-yellow-600 ml-2">+{result.xp_earned} XP</span>
            )}
          </p>
          {!checked.correct && checked.typed && (
            <p className="text-gray-600 mt-1 text-sm">Твой ответ: <span className="font-medium">{checked.typed}</span></p>
          )}
          <p className="text-gray-700 mt-2">Правильно: <span className="font-semibold">{expectedAnswer}</span></p>
        </div>
      )}
    </div>
  )
}

// Idiom/phrase cards: self-grading — show phrase, reveal meaning, user decides
function IdiomCard({ exercise, onAnswer, loading }) {
  const [revealed, setRevealed] = useState(false)

  useEffect(() => {
    setRevealed(false)
  }, [exercise.id ?? exercise.question])

  const handleKnew = () => {
    onAnswer({ user_answer: exercise.correct_answer, quality: 5, autoAdvance: true })
  }

  const handleDidntKnow = () => {
    // quality=3: минимальный порог "правильно" — не попадает в ошибки, но SRS вернёт карточку скоро
    onAnswer({ user_answer: '', quality: 3, autoAdvance: true })
  }

  return (
    <div className="flex flex-col items-center gap-6">
      <div
        className="w-full bg-white rounded-2xl border-2 border-primary-100 flex flex-col items-center justify-center p-8"
        style={{ minHeight: 180 }}
      >
        <p className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Польская идиома</p>
        <p className="text-2xl font-bold text-primary-800 text-center">{exercise.question}</p>
        {exercise.hint && !revealed && (
          <p className="text-sm text-gray-400 mt-3 italic">{exercise.hint}</p>
        )}
      </div>

      {!revealed ? (
        <Button className="w-full" onClick={() => setRevealed(true)} disabled={loading}>
          Показать значение
        </Button>
      ) : (
        <>
          <div className="w-full rounded-xl bg-blue-50 border-2 border-blue-100 p-4 text-center">
            <p className="text-xs text-blue-400 mb-1 uppercase tracking-wide">Значение</p>
            <p className="text-lg font-semibold text-blue-900">{exercise.correct_answer}</p>
            {exercise.translation && exercise.translation !== exercise.correct_answer && (
              <p className="text-sm text-gray-500 mt-1 italic">{exercise.translation}</p>
            )}
          </div>
          <div className="w-full flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={handleDidntKnow} disabled={loading}>
              Не знал
            </Button>
            <Button className="flex-1" onClick={handleKnew} disabled={loading}>
              Знал!
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

export default function Flashcard({ exercise, onAnswer, result, loading }) {
  const isVocabCard = Boolean(exercise.vocab_id)

  if (isVocabCard) {
    return <VocabCard exercise={exercise} onAnswer={onAnswer} result={result} loading={loading} />
  }
  return <IdiomCard exercise={exercise} onAnswer={onAnswer} loading={loading} />
}

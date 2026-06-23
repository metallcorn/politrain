import { useState } from 'react'
import Button from '../ui/Button'
import WordHintText from './WordHintText'

// Reading comprehension: one passage + several multiple-choice questions, scored as a unit.
// The component knows the correct answers (in exercise.questions), so it renders per-question
// feedback locally; the backend call grants XP scaled by how many were right.
export default function ReadingExercise({ exercise, onAnswer, result }) {
  const questions = exercise.questions || []
  const [choices, setChoices] = useState(() => questions.map(() => null))
  const [submitted, setSubmitted] = useState(false)

  const allAnswered = choices.every((c) => c !== null)

  const pick = (qi, opt) => {
    if (submitted) return
    setChoices((c) => c.map((v, i) => (i === qi ? opt : v)))
  }

  const handleSubmit = () => {
    if (!allAnswered || submitted) return
    setSubmitted(true)
    // backend expects a JSON list of chosen option strings, one per question
    onAnswer({ user_answer: JSON.stringify(choices) })
  }

  const correctCount = submitted
    ? questions.reduce((n, q, i) => n + (choices[i] === q.correct_answer ? 1 : 0), 0)
    : 0

  return (
    <div className="flex flex-col gap-4">
      {/* Passage */}
      <div className="card">
        {exercise.title && (
          <h2 className="font-semibold text-gray-900 mb-2">{exercise.title}</h2>
        )}
        <WordHintText
          text={exercise.text}
          wordHints={exercise.word_hints || {}}
          saveToVocab
          className="text-base leading-relaxed text-gray-800"
        />
        {Object.keys(exercise.word_hints || {}).length > 0 && !submitted && (
          <p className="text-xs text-gray-400 mt-2">Подчёркнутые слова — нажми для перевода</p>
        )}
        {submitted && exercise.translation && (
          <p className="text-sm text-gray-400 mt-3 italic border-t pt-2">{exercise.translation}</p>
        )}
      </div>

      {/* Questions */}
      {questions.map((q, qi) => (
        <div key={qi} className="card flex flex-col gap-2">
          <p className="font-medium text-gray-800">{qi + 1}. {q.question}</p>
          <div className="flex flex-col gap-2">
            {q.options.map((opt) => {
              const chosen = choices[qi] === opt
              const isCorrect = opt === q.correct_answer
              let cls = 'border-gray-200 hover:border-primary-300'
              if (submitted) {
                if (isCorrect) cls = 'border-green-400 bg-green-50'
                else if (chosen) cls = 'border-red-400 bg-red-50'
                else cls = 'border-gray-200 opacity-60'
              } else if (chosen) {
                cls = 'border-primary-500 bg-primary-50'
              }
              return (
                <button
                  key={opt}
                  type="button"
                  disabled={submitted}
                  onClick={() => pick(qi, opt)}
                  className={`text-left px-4 py-2.5 rounded-xl border-2 transition-colors ${cls}`}
                >
                  {opt}
                </button>
              )
            })}
          </div>
          {submitted && q.explanation && (
            <p className="text-sm text-gray-500 mt-1">{q.explanation}</p>
          )}
        </div>
      ))}

      {!submitted ? (
        <div className="sticky bottom-4">
          <Button onClick={handleSubmit} disabled={!allAnswered}>
            Проверить
          </Button>
        </div>
      ) : (
        <div className="card text-center bg-primary-50 border-2 border-primary-100">
          <p className="font-bold text-gray-900">
            {correctCount} из {questions.length} верно
          </p>
          {result?.xp_earned > 0 && (
            <p className="text-sm text-yellow-600 font-medium mt-1">+{result.xp_earned} XP</p>
          )}
        </div>
      )}
    </div>
  )
}

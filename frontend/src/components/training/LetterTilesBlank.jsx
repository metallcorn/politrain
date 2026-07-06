import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import Button from '../ui/Button'
import WordHintText from './WordHintText'
import HintButton from './HintButton'
import ExerciseResult from './ExerciseResult'

// Spring for tiles flying between zones + remaining tiles reflowing
const TILE_SPRING = { type: 'spring', stiffness: 500, damping: 34 }

function normalize(s) {
  return (s || '').toLowerCase().trim()
    .replace(/ё/g, 'е')
    .replace(/[.,!?;:]/g, '')
}

export default function LetterTilesBlank({ exercise, onAnswer, result, loading }) {
  const tiles = useMemo(() => {
    const arr = [...exercise.correct_answer.toLowerCase()]
      .map((letter, i) => ({ id: i, letter }))
    // Fisher-Yates shuffle, retry until at least one tile is out of original position
    for (let attempt = 0; attempt < 5; attempt++) {
      for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]]
      }
      if (arr.length <= 1 || arr.some((t, i) => t.id !== i)) break
    }
    return arr
  }, [exercise.correct_answer])

  const [available, setAvailable] = useState(tiles)
  const [arranged, setArranged] = useState([])
  const [submitted, setSubmitted] = useState(false)
  const [hintUsed, setHintUsed] = useState(false)

  const wordHints = exercise.word_hints || {}
  const hasHints = Object.keys(wordHints).length > 0

  const place = (tile) => {
    if (submitted) return
    setAvailable(a => a.filter(t => t.id !== tile.id))
    setArranged(a => [...a, tile])
  }

  const unplace = (tile) => {
    if (submitted) return
    setArranged(a => a.filter(t => t.id !== tile.id))
    setAvailable(a => [...a, tile])
  }

  const handleSubmit = () => {
    if (submitted || loading) return
    setSubmitted(true)
    const userAnswer = arranged.map(t => t.letter).join('')
    onAnswer({ user_answer: userAnswer, hint_used: hintUsed })
  }

  const handleDontKnow = () => {
    if (submitted || loading) return
    setSubmitted(true)
    onAnswer({ user_answer: '', hint_used: hintUsed })
  }

  const tileBase = 'w-11 h-11 rounded-xl text-base font-bold border-2 transition-colors flex items-center justify-center'

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
        {exercise.translation && (
          <p className="text-sm text-gray-400 mt-1 italic">{exercise.translation}</p>
        )}
        {!submitted && (
          <p className="text-xs text-gray-400 mt-1">Нажми на любое слово — покажу перевод (−1 XP)</p>
        )}
        {!submitted && <HintButton hint={exercise.hint} onReveal={() => setHintUsed(true)} />}
      </div>

      {/* Answer zone — fixed min-height so button doesn't jump */}
      <motion.div layout className="min-h-16 border-2 border-dashed border-primary-200 rounded-xl p-3 flex flex-wrap gap-2 content-start bg-primary-50/40">
        {arranged.length === 0 && (
          <p className="text-gray-400 text-sm self-center">Выбирай буквы снизу...</p>
        )}
        {arranged.map(tile => (
          <motion.button
            key={tile.id}
            layoutId={`tile-${tile.id}`}
            layout
            transition={TILE_SPRING}
            whileTap={{ scale: 0.88 }}
            onClick={() => unplace(tile)}
            disabled={submitted}
            className={`${tileBase} bg-primary-800 text-white border-primary-700 hover:bg-primary-700 disabled:opacity-70`}
          >
            {tile.letter}
          </motion.button>
        ))}
      </motion.div>

      {/* Available letters — fixed min-height so layout doesn't collapse */}
      <motion.div layout className="min-h-16 flex flex-wrap gap-2 justify-center content-start">
        {available.map(tile => (
          <motion.button
            key={tile.id}
            layoutId={`tile-${tile.id}`}
            layout
            transition={TILE_SPRING}
            whileTap={{ scale: 0.88 }}
            onClick={() => place(tile)}
            disabled={submitted}
            className={`${tileBase} bg-primary-50 border-primary-300 text-primary-800 hover:bg-primary-100 hover:border-primary-500 disabled:opacity-40`}
          >
            {tile.letter}
          </motion.button>
        ))}
      </motion.div>

      {!submitted && (
        <div className="sticky bottom-4 flex gap-2">
          <Button variant="secondary" className="flex-1" onClick={handleDontKnow} disabled={loading}>
            Не знаю
          </Button>
          <Button
            className="flex-1"
            onClick={handleSubmit}
            disabled={available.length > 0 || loading}
          >
            Проверить
          </Button>
        </div>
      )}

      <ExerciseResult result={result} hintUsed={hintUsed} />
    </div>
  )
}

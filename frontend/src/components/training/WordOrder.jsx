import { useState, useMemo } from 'react'
import { motion } from 'framer-motion'
import { Languages } from 'lucide-react'
import Button from '../ui/Button'
import ExerciseResult from './ExerciseResult'

// Spring for words flying between zones + remaining words reflowing
const WORD_SPRING = { type: 'spring', stiffness: 500, damping: 34 }

export default function WordOrder({ exercise, onAnswer, result }) {
  // Per-word translations for the chips (feedback #110: "не помню как будет 'висит'").
  // word_hints keys are lemmas; match an inflected chip by exact or stem (shared prefix).
  const wordHints = exercise.word_hints || {}
  const hintEntries = Object.entries(wordHints).map(([k, v]) => [k.toLowerCase(), v])
  const [showTranslations, setShowTranslations] = useState(false)
  const translateWord = (raw) => {
    const w = raw.toLowerCase().replace(/[.,!?;:()]/g, '')
    const exact = hintEntries.find(([k]) => k === w)
    if (exact) return exact[1]
    const stem = hintEntries.find(([k]) => {
      const m = Math.min(k.length, w.length)
      if (m < 4) return false
      let cp = 0
      while (cp < k.length && cp < w.length && k[cp] === w[cp]) cp++
      return cp >= 3 && cp >= m - 3
    })
    return stem ? stem[1] : null
  }
  // Support both "[word1, word2]" format and "word1 / word2 / word3" format
  const bracketMatch = exercise.question.match(/\[([^\]]+)\]/)
  const words = bracketMatch
    ? bracketMatch[1].split(/[,/]+/).map((w) => w.trim()).filter(Boolean)
    : exercise.question.split('/').map((w) => w.replace(/\(.*?\)/g, '').replace(/[?.!]$/,'').trim()).filter(Boolean)

  // Stable unique id per word slot (words can repeat → can't key by string/index)
  const initialTiles = useMemo(
    () => words.map((w, i) => ({ id: i, word: w })).sort(() => Math.random() - 0.5),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [exercise.question]
  )
  const [available, setAvailable] = useState(initialTiles)
  const [arranged, setArranged] = useState([])
  const [submitted, setSubmitted] = useState(false)

  const addWord = (tile) => {
    if (submitted) return
    setAvailable((a) => a.filter((t) => t.id !== tile.id))
    setArranged((a) => [...a, tile])
  }

  const removeWord = (tile) => {
    if (submitted) return
    setArranged((a) => a.filter((t) => t.id !== tile.id))
    setAvailable((a) => [...a, tile])
  }

  const handleSubmit = () => {
    if (arranged.length === 0) return
    setSubmitted(true)
    onAnswer({ user_answer: arranged.map((t) => t.word).join(' ') })
  }

  const hintMatch = exercise.question.match(/\(([^)]+)\)/)
  const questionText = bracketMatch
    ? exercise.question.replace(/\[.*?\]/, '').trim()
    : (hintMatch?.[1] || exercise.hint || 'Составь предложение из слов:')

  const chipBase = 'px-5 py-3 rounded-xl text-base font-medium transition-colors'

  return (
    <div className="flex flex-col gap-4">
      <div className="card">
        <p className="text-sm text-gray-500 mb-1">{questionText}</p>
      </div>

      {/* Answer zone — fixed min-height so button doesn't jump */}
      <motion.div layout className="min-h-24 border-2 border-dashed border-gray-200 rounded-xl p-3 flex flex-wrap gap-2 content-start bg-gray-50">
        {arranged.length === 0 && <p className="text-gray-400 text-sm self-center">Нажимай слова снизу...</p>}
        {arranged.map((tile) => (
          <motion.button
            key={tile.id}
            layoutId={`word-${tile.id}`}
            layout
            transition={WORD_SPRING}
            whileTap={{ scale: 0.92 }}
            onClick={() => removeWord(tile)}
            disabled={submitted}
            className={`${chipBase} bg-primary-800 text-white hover:bg-primary-700 disabled:opacity-70`}
          >
            {tile.word}
          </motion.button>
        ))}
      </motion.div>

      {hintEntries.length > 0 && !submitted && (
        <button
          type="button"
          onClick={() => setShowTranslations((v) => !v)}
          className="self-start flex items-center gap-1.5 text-xs text-primary-700 font-medium"
        >
          <Languages size={14} />
          {showTranslations ? 'Скрыть переводы' : 'Показать переводы слов'}
        </button>
      )}

      {/* Available words — fixed min-height so layout doesn't collapse as words are picked */}
      <motion.div layout className="min-h-24 flex flex-wrap gap-2 content-start">
        {available.map((tile) => {
          const tr = showTranslations ? translateWord(tile.word) : null
          return (
            <motion.button
              key={tile.id}
              layoutId={`word-${tile.id}`}
              layout
              transition={WORD_SPRING}
              whileTap={{ scale: 0.92 }}
              onClick={() => addWord(tile)}
              disabled={submitted}
              className={`${chipBase} flex flex-col items-center bg-white border-2 border-gray-200 hover:border-primary-400 hover:bg-primary-50 disabled:opacity-50`}
            >
              <span>{tile.word}</span>
              {tr && <span className="text-[11px] font-normal text-gray-400 mt-0.5">{tr}</span>}
            </motion.button>
          )
        })}
      </motion.div>

      {!submitted && (
        <div className="sticky bottom-4">
          <Button onClick={handleSubmit} disabled={arranged.length === 0}>
            Проверить
          </Button>
        </div>
      )}

      <ExerciseResult
        result={result}
        variants={result && !result.is_correct && result.correct_answer
          ? result.correct_answer.split(' / ').map(s => s.trim()).filter(Boolean)
          : null}
        translation={exercise.translation}
      />
    </div>
  )
}

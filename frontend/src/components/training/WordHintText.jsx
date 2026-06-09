import { useState } from 'react'
import { vocabApi } from '../../api'

// Splits text into word/space tokens and makes hintable words clickable.
// wordHints: { "word": "translation" } — keys are usually dictionary (lemma) forms.
// onHintUsed: called once on first click (for -1 XP tracking)
// saveToVocab: if true, auto-saves clicked word to user vocabulary pool
export default function WordHintText({ text, wordHints = {}, onHintUsed, saveToVocab = false, className = '' }) {
  const [activeHint, setActiveHint] = useState(null)
  const [hintFired, setHintFired] = useState(false)
  const [savedWords, setSavedWords] = useState(new Set())

  if (!text) return null

  const hints = Object.fromEntries(
    Object.entries(wordHints).map(([k, v]) => [k.toLowerCase(), v])
  )
  const hintKeys = Object.keys(hints)

  const tokens = text.split(/(\s+)/)
  const normalize = (w) => w.toLowerCase().replace(/[.,!?;:«»"'()[\]…—–]/g, '')

  const commonPrefix = (a, b) => {
    let i = 0
    while (i < a.length && i < b.length && a[i] === b[i]) i++
    return i
  }

  // Resolve a displayed word to a hint. Exact match first; otherwise stem match —
  // an inflected form (zupę) shares a long prefix with its lemma key (zupa) and differs
  // only in the suffix. Requires both ≥4 chars and a shared prefix covering all but ≤3
  // trailing chars, so unrelated words (samochód vs sukienka) don't false-match.
  const resolveHint = (word) => {
    if (!word) return null
    if (hints[word] !== undefined) return { key: word, translation: hints[word] }
    for (const k of hintKeys) {
      const m = Math.min(word.length, k.length)
      if (m < 4) continue
      const cp = commonPrefix(word, k)
      if (cp >= 3 && cp >= m - 3) return { key: k, translation: hints[k] }
    }
    return null
  }

  const handleClick = (raw) => {
    const word = normalize(raw)
    const hit = resolveHint(word)
    if (!hit) return
    const cleanWord = raw.replace(/[.,!?;:«»"'()[\]…—–]/g, '')
    setActiveHint(activeHint?.word === word ? null : { word, raw: cleanWord, translation: hit.translation })
    if (!hintFired) {
      setHintFired(true)
      onHintUsed?.()
    }
    if (saveToVocab && !savedWords.has(word)) {
      setSavedWords(prev => new Set([...prev, word]))
      vocabApi.learnWord({ word: cleanWord, translation: hit.translation }).catch(() => {})
    }
  }

  return (
    <div>
      <p className={className}>
        {tokens.map((token, i) => {
          if (/^\s+$/.test(token)) return token
          const hasHint = Boolean(resolveHint(normalize(token)))
          return (
            <span
              key={i}
              onClick={hasHint ? () => handleClick(token) : undefined}
              className={
                hasHint
                  ? 'cursor-pointer underline decoration-dotted decoration-primary-400 underline-offset-4 hover:text-primary-700 transition-colors'
                  : undefined
              }
            >
              {token}
            </span>
          )
        })}
      </p>
      {activeHint && (
        <div className="mt-2 inline-flex items-center gap-2 bg-blue-50 border border-blue-200 rounded-lg px-3 py-1.5 text-sm animate-fade-in">
          <span className="font-medium text-blue-800">{activeHint.raw}</span>
          <span className="text-gray-400">→</span>
          <span className="text-gray-700">{activeHint.translation}</span>
          {saveToVocab && savedWords.has(activeHint.word) && (
            <span className="text-xs text-green-600 ml-1" title="Добавлено в словарь">📚</span>
          )}
        </div>
      )}
    </div>
  )
}

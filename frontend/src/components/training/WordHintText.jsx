import { useState } from 'react'
import { vocabApi } from '../../api'

// Splits text into word/space tokens and makes EVERY word clickable.
// wordHints: { "word": "translation" } — pre-generated hints (dotted underline).
// Words without a pre-hint are fetched on demand from /vocabulary/word-translation
// (cached server-side) — the user can translate ANY word of the sentence, not just
// the ones Mistral happened to hint (user feedback 2026-07-06).
// onHintUsed: called once on first click (for -1 XP tracking)
// saveToVocab: if true, auto-saves clicked word to user vocabulary pool
// fetchMissing: set false when the text is in the user's native language
//   (TranslatePhrase) — fetching would be nonsense there.
export default function WordHintText({ text, wordHints = {}, onHintUsed, saveToVocab = false, fetchMissing = true, className = '' }) {
  const [activeHint, setActiveHint] = useState(null)
  const [hintFired, setHintFired] = useState(false)
  const [savedWords, setSavedWords] = useState(new Set())
  const [fetched, setFetched] = useState({}) // word → translation (session-local cache)

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
    if (fetched[word] !== undefined) return { key: word, translation: fetched[word] }
    return null
  }

  // A word qualifies for on-demand lookup when it's a Polish-side token: Latin letters,
  // not a number/blank. Cyrillic words are the user's own language — skip.
  const canFetch = (word) =>
    fetchMissing && word.length >= 2 && !/[а-яёА-ЯЁ]/.test(word) && /[a-ząćęłńóśźż]/i.test(word) && word !== '___'

  const fireHintUsed = () => {
    if (!hintFired) {
      setHintFired(true)
      onHintUsed?.()
    }
  }

  const saveWord = (word, cleanWord, translation) => {
    if (saveToVocab && !savedWords.has(word)) {
      setSavedWords(prev => new Set([...prev, word]))
      vocabApi.learnWord({ word: cleanWord, translation }).catch(() => {})
    }
  }

  const handleClick = (raw) => {
    const word = normalize(raw)
    const cleanWord = raw.replace(/[.,!?;:«»"'()[\]…—–]/g, '')
    if (activeHint?.word === word) {
      setActiveHint(null)
      return
    }
    const hit = resolveHint(word)
    if (hit) {
      setActiveHint({ word, raw: cleanWord, translation: hit.translation })
      fireHintUsed()
      saveWord(word, cleanWord, hit.translation)
      return
    }
    if (!canFetch(word)) return
    setActiveHint({ word, raw: cleanWord, translation: null }) // null → loading state
    fireHintUsed()
    vocabApi.wordTranslation({ word: cleanWord, context: text })
      .then(res => {
        const tr = res.data?.translation
        if (!tr) throw new Error('empty')
        setFetched(prev => ({ ...prev, [word]: tr }))
        setActiveHint(prev => (prev?.word === word ? { ...prev, translation: tr } : prev))
        saveWord(word, cleanWord, tr)
      })
      .catch(() => {
        setActiveHint(prev => (prev?.word === word ? { ...prev, translation: '—' } : prev))
      })
  }

  return (
    <div>
      <p className={className}>
        {tokens.map((token, i) => {
          if (/^\s+$/.test(token)) return token
          const word = normalize(token)
          const hasHint = Boolean(resolveHint(word))
          const clickable = hasHint || canFetch(word)
          return (
            <span
              key={i}
              onClick={clickable ? () => handleClick(token) : undefined}
              className={
                hasHint
                  ? 'cursor-pointer underline decoration-dotted decoration-primary-400 underline-offset-4 hover:text-primary-700 transition-colors'
                  : clickable
                    ? 'cursor-pointer hover:text-primary-700 hover:underline hover:decoration-dotted hover:underline-offset-4 transition-colors'
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
          {activeHint.translation === null
            ? <span className="text-gray-400 animate-pulse">ищу перевод…</span>
            : <span className="text-gray-700">{activeHint.translation}</span>}
          {saveToVocab && savedWords.has(activeHint.word) && (
            <span className="text-xs text-green-600 ml-1" title="Добавлено в словарь">📚</span>
          )}
        </div>
      )}
    </div>
  )
}

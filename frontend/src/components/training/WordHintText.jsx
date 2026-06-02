import { useState } from 'react'

// Splits text into word/space tokens and makes hintable words clickable.
// wordHints: { "word": "translation" }
// onHintUsed: called once on first click
export default function WordHintText({ text, wordHints = {}, onHintUsed, className = '' }) {
  const [activeHint, setActiveHint] = useState(null)
  const [hintFired, setHintFired] = useState(false)

  if (!text) return null

  const hints = Object.fromEntries(
    Object.entries(wordHints).map(([k, v]) => [k.toLowerCase(), v])
  )

  const tokens = text.split(/(\s+)/)

  const normalize = (w) => w.toLowerCase().replace(/[.,!?;:«»"'()[\]…—–]/g, '')

  const handleClick = (raw) => {
    const key = normalize(raw)
    const translation = hints[key]
    if (!translation) return
    setActiveHint(activeHint?.key === key ? null : { key, raw: raw.replace(/[.,!?;:«»"'()[\]…—–]/g, ''), translation })
    if (!hintFired) {
      setHintFired(true)
      onHintUsed?.()
    }
  }

  return (
    <div>
      <p className={className}>
        {tokens.map((token, i) => {
          if (/^\s+$/.test(token)) return token
          const key = normalize(token)
          const hasHint = Boolean(hints[key])
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
        </div>
      )}
    </div>
  )
}

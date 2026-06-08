import { useState } from 'react'
import Markdown from '../ui/Markdown'

// Shared "💡 Показать подсказку (-1 XP)" reveal toggle.
// Collapsed: a small gray button. Expanded: the hint text with a -1 XP note.
//
// Props:
//   hint      — hint text (markdown). If empty, renders nothing.
//   onReveal  — called once when the hint is first shown (for -1 XP tracking)
//   label     — collapsed button label (default "Показать подсказку")
//   revealedPrefix — emoji/prefix before the revealed hint (default "💡")
export default function HintButton({ hint, onReveal, label = 'Показать подсказку', revealedPrefix = '💡' }) {
  const [shown, setShown] = useState(false)
  if (!hint) return null

  if (shown) {
    return (
      <div className="text-sm text-amber-600 mt-2 animate-fade-in">
        {revealedPrefix} <Markdown className="inline">{hint}</Markdown> <span className="text-xs opacity-60">(-1 XP)</span>
      </div>
    )
  }

  return (
    <button
      onClick={() => { setShown(true); onReveal?.() }}
      className="text-xs text-gray-400 hover:text-amber-500 transition-colors mt-2 flex items-center gap-1"
    >
      💡 {label} <span className="opacity-60">(-1 XP)</span>
    </button>
  )
}

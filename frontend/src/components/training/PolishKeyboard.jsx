const CHARS = ['ą', 'ć', 'ę', 'ł', 'ń', 'ó', 'ś', 'ź', 'ż']

export default function PolishKeyboard({ inputRef, value, onChange }) {
  const insert = (char) => {
    const el = inputRef?.current
    if (!el) {
      onChange(value + char)
      return
    }
    const start = el.selectionStart ?? value.length
    const end = el.selectionEnd ?? value.length
    const next = value.slice(0, start) + char + value.slice(end)
    onChange(next)
    setTimeout(() => {
      el.focus()
      el.setSelectionRange(start + 1, start + 1)
    }, 0)
  }

  return (
    <div className="flex flex-wrap gap-1">
      {CHARS.map((c) => (
        <button
          key={c}
          type="button"
          onMouseDown={(e) => {
            e.preventDefault()
            insert(c)
          }}
          className="w-8 h-8 text-sm font-semibold bg-gray-100 hover:bg-primary-50 hover:text-primary-800 border border-gray-200 hover:border-primary-300 rounded-lg transition-colors select-none"
        >
          {c}
        </button>
      ))}
    </div>
  )
}

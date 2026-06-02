export default function TopicSuggestions({ topics, onSelect }) {
  return (
    <div className="p-4">
      <p className="text-sm text-gray-500 mb-3">Выбери тему для разговора:</p>
      <div className="flex flex-col gap-2">
        {topics.map((topic) => (
          <button
            key={topic}
            onClick={() => onSelect(topic)}
            className="text-left px-4 py-3 rounded-xl border border-gray-200 hover:border-primary-400 hover:bg-primary-50 text-sm text-gray-700 transition-colors"
          >
            {topic}
          </button>
        ))}
      </div>
    </div>
  )
}

import ReactMarkdown from 'react-markdown'

export default function Markdown({ children, className = '' }) {
  if (!children) return null
  return (
    <ReactMarkdown
      className={className}
      components={{
        p:      ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em:     ({ children }) => <em className="italic">{children}</em>,
        ul:     ({ children }) => <ul className="list-disc pl-4 mb-1 space-y-0.5">{children}</ul>,
        ol:     ({ children }) => <ol className="list-decimal pl-4 mb-1 space-y-0.5">{children}</ol>,
        li:     ({ children }) => <li>{children}</li>,
        code:   ({ children }) => <code className="bg-gray-100 rounded px-1 font-mono text-[0.85em]">{children}</code>,
        a:      ({ href, children }) => <a href={href} className="text-primary-600 underline" target="_blank" rel="noopener noreferrer">{children}</a>,
      }}
    >
      {children}
    </ReactMarkdown>
  )
}

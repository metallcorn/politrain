import { useState } from 'react'
import { MessageSquarePlus, X, Send } from 'lucide-react'
import { adminApi } from '../../api'
import Button from '../ui/Button'

export default function FeedbackButton() {
  const [open, setOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)

  const handleOpen = () => {
    setSent(false)
    setComment('')
    setOpen(true)
  }

  const handleSubmit = async () => {
    if (!comment.trim()) return
    setSending(true)
    try {
      const url = window.location.href
      const pageSnapshot = document.querySelector('main')?.innerText?.slice(0, 1000) || ''
      await adminApi.submitFeedback({ comment: comment.trim(), url, page_snapshot: pageSnapshot })
      setSent(true)
      setTimeout(() => setOpen(false), 1500)
    } catch (e) {
      console.error('Feedback error:', e)
    } finally {
      setSending(false)
    }
  }

  return (
    <>
      <button
        onClick={handleOpen}
        className="fixed bottom-20 right-4 md:bottom-6 z-40 bg-primary-800 text-white rounded-full p-3 shadow-lg hover:bg-primary-900 transition-colors"
        title="Обратная связь"
      >
        <MessageSquarePlus size={20} />
      </button>

      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-4 md:items-center bg-black/50" onClick={() => setOpen(false)}>
          <div
            className="bg-white rounded-2xl shadow-xl w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-5 border-b border-gray-100">
              <h2 className="text-lg font-semibold">Обратная связь</h2>
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="p-5 flex flex-col gap-4">
              {sent ? (
                <p className="text-center text-green-600 font-medium py-4">Отправлено!</p>
              ) : (
                <>
                  <p className="text-sm text-gray-500">
                    Опиши проблему или что хочешь улучшить. URL и содержимое страницы сохранятся автоматически.
                  </p>
                  <textarea
                    className="w-full border border-gray-200 rounded-xl p-3 text-sm resize-none focus:outline-none focus:border-primary-400"
                    rows={4}
                    placeholder="Что не так или что стоит улучшить?"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    autoFocus
                  />
                  <Button onClick={handleSubmit} loading={sending} disabled={!comment.trim()}>
                    <Send size={15} />
                    Отправить
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

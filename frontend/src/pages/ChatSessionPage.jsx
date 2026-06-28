import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { chatApi } from '../api'
import { useUIStore } from '../store'
import MessageBubble from '../components/chat/MessageBubble'
import Spinner from '../components/ui/Spinner'
import Modal from '../components/ui/Modal'
import Markdown from '../components/ui/Markdown'
import Button from '../components/ui/Button'
import { Send, ArrowLeft, Mic, ClipboardCheck } from 'lucide-react'

export default function ChatSessionPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { addToast } = useUIStore()
  const [session, setSession] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [sending, setSending] = useState(false)
  const [debriefOpen, setDebriefOpen] = useState(false)
  const [debriefText, setDebriefText] = useState('')
  const [debriefing, setDebriefing] = useState(false)
  const bottomRef = useRef(null)

  const isScenario = Boolean(session?.scenario)
  const userMsgCount = messages.filter((m) => m.role === 'user').length

  const handleDebrief = async () => {
    setDebriefOpen(true)
    setDebriefing(true)
    try {
      const res = await chatApi.debrief(id)
      setDebriefText(res.data.text)
    } catch {
      setDebriefText('Не удалось собрать разбор. Попробуй ещё раз позже.')
    } finally {
      setDebriefing(false)
    }
  }

  useEffect(() => {
    chatApi.getSession(id)
      .then((r) => {
        setSession(r.data)
        setMessages(r.data.messages || [])
      })
      .catch(() => addToast('Ошибка загрузки чата', 'error'))
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || sending) return
    const content = input.trim()
    setInput('')
    setSending(true)

    const userMsg = { id: Date.now(), role: 'user', content, created_at: new Date().toISOString() }
    setMessages((m) => [...m, userMsg])

    try {
      const res = await chatApi.sendMessage(id, content)
      const aiMsg = {
        id: Date.now() + 1,
        role: 'assistant',
        content: res.data.assistant_message.content,
        created_at: new Date().toISOString(),
      }
      setMessages((m) => [...m, aiMsg])
    } catch {
      addToast('Ошибка отправки сообщения', 'error')
      setMessages((m) => m.filter((msg) => msg.id !== userMsg.id))
      setInput(content)
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-6rem)]">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 flex-shrink-0">
        <button onClick={() => navigate('/chat')} className="text-gray-400 hover:text-gray-600">
          <ArrowLeft size={20} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-semibold text-gray-900 truncate">
            {isScenario ? '🎭 ' : ''}{session?.topic || 'Свободная беседа'}
          </h1>
          <p className="text-xs text-gray-400">{isScenario ? 'Ролевой диалог · оставайся в роли' : 'Разговор по-польски с AI'}</p>
        </div>
        {isScenario && (
          <button
            onClick={handleDebrief}
            disabled={userMsgCount === 0}
            className="flex items-center gap-1 text-sm px-3 py-1.5 rounded-xl bg-primary-50 text-primary-800 font-medium hover:bg-primary-100 disabled:opacity-40 transition-colors flex-shrink-0"
          >
            <ClipboardCheck size={16} />
            Разбор
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto bg-gray-50 rounded-2xl p-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center gap-3">
            <p className="text-gray-400 text-sm">Начни разговор! Пиши по-польски,</p>
            <p className="text-gray-400 text-sm">AI поможет и исправит ошибки</p>
          </div>
        )}
        {messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)}
        {sending && (
          <div className="flex justify-start mb-3">
            <div className="bg-white border border-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex items-end gap-2 mt-3 flex-shrink-0">
        <button
          className="p-3 rounded-xl text-gray-300 cursor-not-allowed"
          title="STT скоро будет доступно"
          onClick={() => addToast('STT скоро будет доступно', 'info')}
        >
          <Mic size={20} />
        </button>
        <textarea
          className="flex-1 input resize-none min-h-12 max-h-32"
          placeholder="Написать по-польски..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
        />
        <button
          onClick={handleSend}
          disabled={!input.trim() || sending}
          className="p-3 rounded-xl bg-primary-800 text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
        >
          <Send size={20} />
        </button>
      </div>

      <Modal isOpen={debriefOpen} onClose={() => setDebriefOpen(false)} title="Разбор диалога">
        {debriefing ? (
          <div className="flex flex-col items-center gap-3 py-6">
            <Spinner />
            <p className="text-sm text-gray-400">Анализирую твои реплики...</p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="prose prose-sm max-w-none text-gray-700">
              <Markdown>{debriefText}</Markdown>
            </div>
            <Button onClick={() => setDebriefOpen(false)}>Понятно</Button>
          </div>
        )}
      </Modal>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { chatApi } from '../api'
import { useUIStore } from '../store'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Spinner from '../components/ui/Spinner'
import Modal from '../components/ui/Modal'
import TopicSuggestions from '../components/chat/TopicSuggestions'
import { Plus, MessageSquare } from 'lucide-react'

export default function ChatPage() {
  const [sessions, setSessions] = useState([])
  const [topics, setTopics] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const navigate = useNavigate()
  const { addToast } = useUIStore()

  useEffect(() => {
    Promise.all([chatApi.listSessions(), chatApi.getTopics()])
      .then(([s, t]) => {
        setSessions(s.data)
        setTopics(t.data.topics)
      })
      .finally(() => setLoading(false))
  }, [])

  const createSession = async (topic = null) => {
    try {
      const res = await chatApi.createSession(topic)
      navigate(`/chat/${res.data.id}`)
    } catch {
      addToast('Ошибка создания сессии', 'error')
    }
  }

  if (loading) return <div className="flex justify-center py-12"><Spinner /></div>

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Чат</h1>
          <p className="text-gray-500 text-sm mt-0.5">Говори по-польски с AI</p>
        </div>
        <Button onClick={() => setModalOpen(true)}>
          <Plus size={18} />
          Новый
        </Button>
      </div>

      {sessions.length === 0 ? (
        <div className="flex flex-col items-center py-12 gap-4 text-center">
          <MessageSquare size={48} className="text-gray-200" />
          <div>
            <p className="font-medium text-gray-600">Нет сессий</p>
            <p className="text-sm text-gray-400 mt-1">Начни свой первый разговор по-польски!</p>
          </div>
          <Button onClick={() => setModalOpen(true)}>Начать разговор</Button>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {sessions.map((s) => (
            <Card key={s.id} onClick={() => navigate(`/chat/${s.id}`)} className="hover:border-primary-200">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-800">{s.topic || 'Свободная беседа'}</p>
                  <p className="text-sm text-gray-400 mt-0.5">
                    {new Date(s.created_at).toLocaleDateString('ru')} · {s.message_count} сообщений
                  </p>
                </div>
                <MessageSquare size={18} className="text-gray-300" />
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="Новый разговор">
        <div className="flex flex-col gap-4">
          <Button className="w-full" onClick={() => { setModalOpen(false); createSession() }}>
            Свободная тема
          </Button>
          <div className="border-t border-gray-100 pt-4">
            <TopicSuggestions topics={topics} onSelect={(t) => { setModalOpen(false); createSession(t) }} />
          </div>
        </div>
      </Modal>
    </div>
  )
}

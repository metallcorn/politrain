import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore, useUIStore } from '../store'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'

export default function RegisterPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [lang, setLang] = useState('ru')
  const [loading, setLoading] = useState(false)
  const { register } = useAuthStore()
  const { addToast } = useUIStore()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await register(username, password, lang)
      navigate('/onboarding')
    } catch (err) {
      addToast(err.response?.data?.detail || 'Ошибка регистрации', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-white p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <img src="/icon.svg" alt="Politrain" className="w-20 h-20 rounded-2xl mx-auto mb-4 shadow-md" />
          <h1 className="text-2xl font-bold text-gray-900">Politrain</h1>
          <p className="text-green-600 mt-1 italic font-medium">skok po skoku 🐸</p>
          <p className="text-gray-400 text-sm mt-0.5">Начни учить польский сегодня</p>
        </div>

        <form onSubmit={handleSubmit} className="card flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-gray-800">Создать аккаунт</h2>
          <Input
            label="Логин"
            placeholder="username (min 3 символа)"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
          <Input
            label="Пароль"
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
          <div className="flex flex-col gap-1">
            <label className="text-sm font-medium text-gray-700">Родной язык</label>
            <div className="flex gap-3">
              {[{ value: 'ru', label: '🇷🇺 Русский' }, { value: 'en', label: '🇬🇧 English' }].map((l) => (
                <button
                  key={l.value}
                  type="button"
                  onClick={() => setLang(l.value)}
                  className={`flex-1 py-2 rounded-xl border font-medium text-sm transition-colors ${
                    lang === l.value
                      ? 'border-primary-800 bg-primary-50 text-primary-800'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  {l.label}
                </button>
              ))}
            </div>
          </div>
          <Button type="submit" loading={loading} className="w-full">
            Зарегистрироваться
          </Button>
          <p className="text-center text-sm text-gray-500">
            Уже есть аккаунт?{' '}
            <Link to="/login" className="text-primary-800 font-medium hover:underline">
              Войти
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}

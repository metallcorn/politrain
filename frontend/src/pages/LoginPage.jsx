import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore, useUIStore } from '../store'
import Button from '../components/ui/Button'
import Input from '../components/ui/Input'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuthStore()
  const { addToast } = useUIStore()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const user = await login(username, password)
      if (!user.onboarding_done) {
        navigate('/onboarding')
      } else {
        navigate('/dashboard')
      }
    } catch (err) {
      addToast(err.response?.data?.detail || 'Неверный логин или пароль', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-white p-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-primary-800 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <span className="text-white font-bold text-2xl">P</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Politrain</h1>
          <p className="text-gray-500 mt-1">AI-тренажёр польского языка</p>
        </div>

        <form onSubmit={handleSubmit} className="card flex flex-col gap-4">
          <h2 className="text-lg font-semibold text-gray-800">Войти</h2>
          <Input
            label="Логин"
            placeholder="username"
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
            autoComplete="current-password"
            required
          />
          <Button type="submit" loading={loading} className="w-full">
            Войти
          </Button>
          <p className="text-center text-sm text-gray-500">
            Нет аккаунта?{' '}
            <Link to="/register" className="text-primary-800 font-medium hover:underline">
              Зарегистрироваться
            </Link>
          </p>
        </form>
      </div>
    </div>
  )
}

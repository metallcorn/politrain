import { useAuthStore } from '../../store'
import { useNavigate, Link } from 'react-router-dom'
import { LogOut, User } from 'lucide-react'
import XPBar from '../gamification/XPBar'
import StreakCounter from '../gamification/StreakCounter'

export default function Navbar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <header className="hidden md:flex items-center justify-between px-6 py-3 bg-white border-b border-gray-100 sticky top-0 z-10">
      <div className="flex items-center gap-4">
        {user && <XPBar xp={user.xp} />}
      </div>
      <div className="flex items-center gap-4">
        {user && <StreakCounter days={user.streak_days} />}
        <Link to="/profile" className="flex items-center gap-2 text-gray-600 hover:text-primary-800 transition-colors">
          <div className="w-8 h-8 rounded-full bg-primary-800 text-white flex items-center justify-center text-sm font-bold">
            {user?.username?.[0]?.toUpperCase()}
          </div>
        </Link>
        <button onClick={handleLogout} className="text-gray-400 hover:text-gray-600 transition-colors" title="Выйти">
          <LogOut size={20} />
        </button>
      </div>
    </header>
  )
}

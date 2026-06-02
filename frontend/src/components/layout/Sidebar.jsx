import { NavLink } from 'react-router-dom'
import { LayoutDashboard, BookOpen, Dumbbell, MessageSquare, GraduationCap, User } from 'lucide-react'

const links = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Главная' },
  { to: '/topics', icon: BookOpen, label: 'Правила' },
  { to: '/training', icon: Dumbbell, label: 'Тренировка' },
  { to: '/chat', icon: MessageSquare, label: 'Чат' },
  { to: '/exam', icon: GraduationCap, label: 'Экзамен B1' },
  { to: '/profile', icon: User, label: 'Профиль' },
]

export default function Sidebar() {
  return (
    <aside className="hidden md:flex flex-col fixed left-0 top-0 h-screen w-64 bg-white border-r border-gray-100 z-20">
      <div className="flex items-center gap-3 px-6 py-5 border-b border-gray-100">
        <div className="w-8 h-8 bg-primary-800 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">P</span>
        </div>
        <span className="text-xl font-bold text-primary-800">Politrain</span>
      </div>
      <nav className="flex-1 py-4">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-6 py-3 text-sm font-medium transition-colors ${
                isActive
                  ? 'text-primary-800 bg-primary-50 border-r-2 border-primary-800'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`
            }
          >
            <Icon size={20} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-6 py-4 border-t border-gray-100">
        <p className="text-xs text-gray-400">Politrain v1.0</p>
      </div>
    </aside>
  )
}

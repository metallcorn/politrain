import { NavLink } from 'react-router-dom'
import { LayoutDashboard, BookOpen, Dumbbell, MessageSquare, User } from 'lucide-react'

const links = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Главная' },
  { to: '/topics', icon: BookOpen, label: 'Правила' },
  { to: '/training', icon: Dumbbell, label: 'Тренировка' },
  { to: '/chat', icon: MessageSquare, label: 'Чат' },
  { to: '/profile', icon: User, label: 'Профиль' },
]

export default function BottomNav() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-100 z-20 pb-safe">
      <div className="flex">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex-1 flex flex-col items-center py-2 text-xs transition-colors ${
                isActive ? 'text-primary-800' : 'text-gray-400'
              }`
            }
          >
            <Icon size={22} strokeWidth={isActive => isActive ? 2.5 : 1.5} />
            <span className="mt-1">{label}</span>
          </NavLink>
        ))}
      </div>
    </nav>
  )
}

import { Outlet, useLocation } from 'react-router-dom'
import Sidebar from './Sidebar'
import BottomNav from './BottomNav'
import Navbar from './Navbar'
import FeedbackButton from './FeedbackButton'
import { useAuthStore } from '../../store'

export default function Layout() {
  const { user } = useAuthStore()
  const location = useLocation()
  return (
    <div className="min-h-screen flex">
      <Sidebar />
      <div className="flex-1 flex flex-col md:ml-64 min-w-0">
        <Navbar />
        <main className="flex-1 p-4 pb-24 md:pb-6 max-w-4xl w-full mx-auto overflow-x-hidden">
          <div key={location.pathname} className="animate-fade-in">
            <Outlet />
          </div>
        </main>
      </div>
      <BottomNav />
      {user?.is_admin && <FeedbackButton />}
    </div>
  )
}

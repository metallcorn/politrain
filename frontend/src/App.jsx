import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import OnboardingPage from './pages/OnboardingPage'
import DashboardPage from './pages/DashboardPage'
import TopicsPage from './pages/TopicsPage'
import TopicDetailPage from './pages/TopicDetailPage'
import TrainingPage from './pages/TrainingPage'
import TrainingSessionPage from './pages/TrainingSessionPage'
import ChatPage from './pages/ChatPage'
import ChatSessionPage from './pages/ChatSessionPage'
import ExamPage from './pages/ExamPage'
import ExamTaskPage from './pages/ExamTaskPage'
import ProfilePage from './pages/ProfilePage'
import AdminPage from './pages/AdminPage'
import Toast from './components/ui/Toast'
import Spinner from './components/ui/Spinner'

function ProtectedRoute({ children }) {
  const { user, token, loading } = useAuthStore()
  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner /></div>
  if (!token || !user) return <Navigate to="/login" replace />
  if (!user.onboarding_done) return <Navigate to="/onboarding" replace />
  return children
}

function AuthRoute({ children }) {
  const { user, token, loading } = useAuthStore()
  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner /></div>
  if (token && user) {
    if (!user.onboarding_done) return <Navigate to="/onboarding" replace />
    return <Navigate to="/dashboard" replace />
  }
  return children
}

function OnboardingRoute({ children }) {
  const { token, loading } = useAuthStore()
  if (loading) return <div className="min-h-screen flex items-center justify-center"><Spinner /></div>
  if (!token) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  const { fetchMe, token } = useAuthStore()

  useEffect(() => {
    if (token) fetchMe()
    else useAuthStore.setState({ loading: false })
  }, [])

  return (
    <BrowserRouter>
      <Toast />
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/login" element={<AuthRoute><LoginPage /></AuthRoute>} />
        <Route path="/register" element={<AuthRoute><RegisterPage /></AuthRoute>} />
        <Route path="/onboarding" element={<OnboardingRoute><OnboardingPage /></OnboardingRoute>} />
        <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/topics" element={<TopicsPage />} />
          <Route path="/topics/:slug" element={<TopicDetailPage />} />
          <Route path="/training" element={<TrainingPage />} />
          <Route path="/training/session" element={<TrainingSessionPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:id" element={<ChatSessionPage />} />
          <Route path="/exam" element={<ExamPage />} />
          <Route path="/exam/:type" element={<ExamTaskPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

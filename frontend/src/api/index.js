import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 35000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = err.config?.url || ''
    const isAuthCall = url.includes('/auth/login') || url.includes('/auth/register')
    // Session-expiry handling only for NON-auth calls: an expired token on a
    // background request clears it and bounces to /login. A 401 on the login
    // request itself is "wrong password" — let the page show its own error,
    // never hard-reload (that caused the flicker/loop). Also skip the redirect
    // if we're already on an auth page.
    if (err.response?.status === 401 && !isAuthCall) {
      localStorage.removeItem('token')
      const p = window.location.pathname
      if (!p.startsWith('/login') && !p.startsWith('/register')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// Human-readable reason for a failed request. Distinguishes a real server
// response (e.g. 401 wrong password) from a request that never reached the
// server — typically a stale service worker / offline cache eating the fetch,
// which used to surface as a misleading "wrong password" toast.
export function errorMessage(err, fallback = 'Что-то пошло не так') {
  if (err.response) return err.response.data?.detail || fallback
  return 'Сервер не отвечает. Обнови страницу (Ctrl+Shift+R); если не помогло — очисти данные сайта в настройках браузера.'
}

export default api

// Auth
export const authApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  logout: () => api.post('/auth/logout'),
}

// Onboarding
export const onboardingApi = {
  status: () => api.get('/onboarding/status'),
  saveSettings: (data) => api.post('/onboarding/settings', data),
  getTest: () => api.get('/onboarding/placement-test'),
  submitTest: (data) => api.post('/onboarding/placement-test', data),
}

// Topics
export const topicsApi = {
  list: () => api.get('/topics'),
  get: (slug) => api.get(`/topics/${slug}`),
  getLesson: (slug) => api.get(`/topics/${slug}/lesson`),
  nextExample: (slug) => api.post(`/topics/${slug}/lesson/next`),
  complete: (slug) => api.post(`/topics/${slug}/complete`),
  reportExercise: (id, comment) => api.post(`/topics/exercises/${id}/report`, { comment }),
}

// Vocabulary
export const vocabApi = {
  list: () => api.get('/vocabulary'),
  due: () => api.get('/vocabulary/due'),
  review: (id, quality) => api.post(`/vocabulary/${id}/review`, { quality }),
  stats: () => api.get('/vocabulary/stats'),
  learnWord: (data) => api.post('/vocabulary/learn-word', data),
}

// Training
export const trainingApi = {
  session: (mode = 'daily', topic = null) => api.get(`/training/session?mode=${mode}${topic ? `&topic=${topic}` : ''}`, { timeout: ['bonus', 'new', 'daily', 'topic'].includes(mode) ? 85000 : 30000 }),
  answer: (data) => api.post('/training/answer', data),
  stats: () => api.get('/training/stats'),
  report: (data) => api.post('/training/report', data),
  sessionComplete: (data) => api.post('/training/session-complete', data),
  sessionRating: (data) => api.post('/training/session-rating', data),
  explain: (data) => api.post('/training/explain', data, { timeout: 30000 }),
}

// Chat
export const chatApi = {
  createSession: (topic) => api.post('/chat/session', { topic }),
  listSessions: () => api.get('/chat/sessions'),
  getSession: (id) => api.get(`/chat/session/${id}`),
  sendMessage: (id, content) => api.post(`/chat/session/${id}/message`, { content }),
  getTopics: () => api.get('/chat/topics'),
}

// Exam
export const examApi = {
  tasks: () => api.get('/exam/tasks'),
  getTask: (type) => api.get(`/exam/task/${type}`),
  submit: (type, data) => api.post(`/exam/task/${type}/submit`, data),
}

// Admin feedback
export const adminApi = {
  submitFeedback: (data) => api.post('/admin/feedback', data),
  getFeedback: (resolved = false) => api.get(`/admin/feedback?resolved=${resolved}`),
  resolveFeedback: (id) => api.patch(`/admin/feedback/${id}/resolve`),
  mistralUsage: (days = 30) => api.get(`/admin/mistral-usage?days=${days}`),
  poolStats: () => api.get('/admin/exercise-pool/stats'),
  togglePool: (id) => api.post(`/admin/exercise-pool/${id}/toggle`),
}

// Profile
export const profileApi = {
  get: () => api.get('/profile'),
  achievements: () => api.get('/profile/achievements'),
  activity: () => api.get('/profile/activity'),
  dashboard: () => api.get('/profile/dashboard'),
  leaderboard: () => api.get('/profile/leaderboard'),
  weakSpots: () => api.get('/profile/weak-spots'),
  updateSettings: (data) => api.put('/profile/settings', data),
  getPreferences: () => api.get('/profile/content-preferences'),
  updatePreferences: (data) => api.put('/profile/content-preferences', data),
}

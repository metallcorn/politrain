import { create } from 'zustand'
import { authApi } from '../api'

export const useAuthStore = create((set, get) => ({
  user: null,
  token: localStorage.getItem('token'),
  loading: true,

  setToken: (token) => {
    localStorage.setItem('token', token)
    set({ token })
  },

  setUser: (user) => set({ user }),

  login: async (username, password) => {
    const res = await authApi.login({ username, password })
    const { access_token } = res.data
    localStorage.setItem('token', access_token)
    set({ token: access_token })
    const me = await authApi.me()
    set({ user: me.data })
    return me.data
  },

  register: async (username, password, nativeLanguage) => {
    const res = await authApi.register({ username, password, native_language: nativeLanguage })
    const { access_token } = res.data
    localStorage.setItem('token', access_token)
    set({ token: access_token })
    const me = await authApi.me()
    set({ user: me.data })
    return me.data
  },

  logout: () => {
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },

  fetchMe: async () => {
    try {
      const res = await authApi.me()
      set({ user: res.data, loading: false })
      return res.data
    } catch {
      set({ user: null, token: null, loading: false })
      localStorage.removeItem('token')
      return null
    }
  },
}))

export const useUIStore = create((set) => ({
  toasts: [],
  addToast: (message, type = 'info') => {
    const id = Date.now()
    set((s) => ({ toasts: [...s.toasts, { id, message, type }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 4000)
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

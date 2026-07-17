import { useEffect, useState } from 'react'
import { profileApi, authApi } from '../api'
import { useAuthStore } from '../store'
import { useNavigate } from 'react-router-dom'
import Card from '../components/ui/Card'
import ProgressBar from '../components/ui/ProgressBar'
import AchievementBadge from '../components/gamification/AchievementBadge'
import ActivityDashboard from '../components/gamification/ActivityDashboard'
import Leaderboard from '../components/gamification/Leaderboard'
import Skeleton from '../components/ui/Skeleton'
import Button from '../components/ui/Button'
import InstallPwa from '../components/InstallPwa'
import { Zap, Flame, Target, LogOut, Settings, ShieldCheck, Clock } from 'lucide-react'

const LANGUAGES = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
  { code: 'uk', label: 'Українська' },
  { code: 'de', label: 'Deutsch' },
]

const INTEREST_THEMES = [
  { key: 'IT и технологии', emoji: '💻' },
  { key: 'Путешествия', emoji: '✈️' },
  { key: 'Шоппинг и магазины', emoji: '🛍️' },
  { key: 'Рестораны и кафе', emoji: '☕' },
  { key: 'Работа и карьера', emoji: '💼' },
  { key: 'Здоровье и медицина', emoji: '🏥' },
  { key: 'Спорт и активный отдых', emoji: '🏃' },
  { key: 'Банки и финансы', emoji: '🏦' },
  { key: 'Транспорт и ПДД', emoji: '🚗' },
  { key: 'Культура и история', emoji: '🎭' },
  { key: 'Дом и быт', emoji: '🏠' },
  { key: 'Семья и отношения', emoji: '👨‍👩‍👧' },
]

export default function ProfilePage() {
  const { user, logout, fetchMe } = useAuthStore()
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [achievements, setAchievements] = useState([])
  const [dashboardData, setDashboardData] = useState(null)
  const [leaderboardData, setLeaderboardData] = useState(null)
  const [prefs, setPrefs] = useState(null)
  const [loading, setLoading] = useState(true)
  const [savingLang, setSavingLang] = useState(false)
  const [savingThemes, setSavingThemes] = useState(false)
  const [selectedLang, setSelectedLang] = useState(user?.native_language || 'ru')
  const [selectedThemes, setSelectedThemes] = useState([])

  useEffect(() => {
    Promise.allSettled([
      profileApi.get(),
      profileApi.achievements(),
      profileApi.dashboard(),
      profileApi.getPreferences(),
      profileApi.leaderboard(),
    ]).then(([p, a, dash, pref, lb]) => {
      if (p.status === 'fulfilled') {
        setProfile(p.value.data)
        setSelectedLang(p.value.data.native_language || 'ru')
      }
      if (a.status === 'fulfilled') setAchievements(a.value.data)
      if (dash.status === 'fulfilled') setDashboardData(dash.value.data)
      if (pref.status === 'fulfilled') {
        setPrefs(pref.value.data)
        setSelectedThemes(pref.value.data.interest_themes || [])
      }
      if (lb.status === 'fulfilled') setLeaderboardData(lb.value.data)
    }).finally(() => setLoading(false))
  }, [])

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const handleSaveLang = async () => {
    setSavingLang(true)
    try {
      await profileApi.updateSettings({ native_language: selectedLang })
      await fetchMe()
    } finally {
      setSavingLang(false)
    }
  }

  const toggleTheme = (key) => {
    setSelectedThemes((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    )
  }

  const handleSaveThemes = async () => {
    setSavingThemes(true)
    try {
      await profileApi.updatePreferences({
        conversational_weight: prefs?.conversational_weight ?? 0.25,
        idiom_weight: prefs?.idiom_weight ?? 0.25,
        situational_weight: prefs?.situational_weight ?? 0.25,
        grammar_weight: prefs?.grammar_weight ?? 0.25,
        session_length: prefs?.session_length ?? 'standard',
        daily_goal_minutes: prefs?.daily_goal_minutes ?? 15,
        interest_themes: selectedThemes,
      })
    } finally {
      setSavingThemes(false)
    }
  }

  if (loading) return (
    <div className="flex flex-col gap-4 animate-fade-in">
      <Skeleton className="h-7 w-28 rounded-lg" />
      <div className="grid grid-cols-3 gap-3">
        {[1,2,3].map(i => (
          <div key={i} className="bg-white rounded-2xl border border-gray-100 p-4 flex flex-col gap-2 items-center">
            <Skeleton className="h-7 w-12 rounded" />
            <Skeleton className="h-3 w-16 rounded" />
          </div>
        ))}
      </div>
      <Skeleton className="h-3 w-full rounded-full" />
      <div className="bg-white rounded-2xl border border-gray-100 p-4 flex flex-col gap-3">
        <Skeleton className="h-5 w-32 rounded" />
        <div className="flex gap-2 flex-wrap">
          {[1,2,3,4,5,6].map(i => <Skeleton key={i} className="h-10 w-10 rounded-xl" />)}
        </div>
      </div>
      <div className="bg-white rounded-2xl border border-gray-100 p-4 flex flex-col gap-3">
        <Skeleton className="h-5 w-24 rounded" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </div>
    </div>
  )

  const earnedAchievements = achievements.filter((a) => a.earned)
  const lockedAchievements = achievements.filter((a) => !a.earned)

  const rankStart = profile?.xp_rank_start || 0
  const xpInLevel = Math.max(0, (profile?.xp || 0) - rankStart)
  const xpNeeded = xpInLevel + (profile?.xp_to_next_level || 1)

  const themesChanged = JSON.stringify(selectedThemes.slice().sort()) !==
    JSON.stringify((prefs?.interest_themes || []).slice().sort())

  const formatTrainingTime = (seconds) => {
    if (!seconds) return null
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    if (h > 0) return `${h} ч${m > 0 ? ` ${m} мин` : ''}`
    return `${m} мин`
  }

  return (
    <div className="flex flex-col gap-5 pb-6">
      {/* Avatar + basic info */}
      <Card className="flex items-center gap-4">
        <div className="w-16 h-16 rounded-2xl bg-primary-800 text-white flex items-center justify-center text-2xl font-bold flex-shrink-0">
          {user?.username?.[0]?.toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 truncate">{user?.username}</h1>
          <p className="text-sm text-gray-500">Уровень польского: <strong className="text-primary-800">{user?.level}</strong></p>
          <p className="text-xs text-gray-400 mt-0.5">
            На Politrain с {new Date(user?.created_at).toLocaleDateString('ru', { month: 'long', year: 'numeric' })}
          </p>
        </div>
      </Card>

      {/* XP & Game level */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Zap size={18} className="text-yellow-500" />
            <span className="font-semibold text-gray-800">{profile?.game_level_name}</span>
            <span className="text-sm text-gray-400">({profile?.game_level}/25)</span>
          </div>
          <span className="font-bold text-gray-700">{profile?.xp} XP</span>
        </div>
        <ProgressBar value={xpInLevel} max={xpNeeded} />
        <p className="text-xs text-gray-400 mt-1">
          {profile?.xp_to_next_level > 0
            ? `Ещё ${profile?.xp_to_next_level} XP до следующего ранга`
            : 'Максимальный ранг достигнут!'}
        </p>
      </Card>

      {/* Streak */}
      <Card className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-xl bg-orange-50 flex items-center justify-center flex-shrink-0">
          <Flame size={24} className={profile?.streak_days > 0 ? 'text-orange-500' : 'text-gray-300'} />
        </div>
        <div>
          <p className="text-2xl font-black text-orange-500">{profile?.streak_days}</p>
          <p className="text-sm text-gray-500">дней подряд</p>
        </div>
      </Card>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <Card className="text-center py-3">
          <p className="text-xl font-bold text-primary-800">{profile?.total_exercises || 0}</p>
          <p className="text-xs text-gray-500">Упражнений</p>
        </Card>
        <Card className="text-center py-3">
          <p className="text-xl font-bold text-primary-800">{profile?.vocab_count || 0}</p>
          <p className="text-xs text-gray-500">Слов</p>
        </Card>
        <Card className="text-center py-3">
          <p className="text-xl font-bold text-primary-800">{profile?.total_chat_messages || 0}</p>
          <p className="text-xs text-gray-500">Сообщений</p>
        </Card>
      </div>

      {/* Learning time */}
      {formatTrainingTime(profile?.total_training_seconds) && (
        <Card className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center flex-shrink-0">
            <Clock size={20} className="text-blue-400" />
          </div>
          <div>
            <p className="text-xl font-bold text-primary-800">{formatTrainingTime(profile?.total_training_seconds)}</p>
            <p className="text-xs text-gray-500">Время обучения</p>
          </div>
        </Card>
      )}

      {/* Progress to B1 */}
      <Card>
        <div className="flex items-center gap-2 mb-2">
          <Target size={18} className="text-primary-800" />
          <span className="font-semibold text-gray-800">Прогресс к B1</span>
          <span className="ml-auto font-bold text-primary-800">{profile?.progress_to_b1}%</span>
        </div>
        <ProgressBar value={profile?.progress_to_b1 || 0} max={100} />
      </Card>

      {/* Activity dashboard */}
      <div>
        <h2 className="font-semibold text-gray-800 mb-3">Активность</h2>
        {loading ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-20 rounded-2xl" />
            <Skeleton className="h-32 rounded-2xl" />
            <Skeleton className="h-24 rounded-2xl" />
          </div>
        ) : (
          <ActivityDashboard data={dashboardData} />
        )}
      </div>

      {/* Leaderboard */}
      {leaderboardData && <Leaderboard data={leaderboardData} />}

      {/* Achievements */}
      {achievements.length > 0 && (
        <div>
          <h2 className="font-semibold text-gray-800 mb-3">
            Достижения ({earnedAchievements.length}/{achievements.length})
          </h2>
          <div className="grid grid-cols-3 gap-2">
            {earnedAchievements.map((a) => <AchievementBadge key={a.id} achievement={a} earned />)}
            {lockedAchievements.map((a) => <AchievementBadge key={a.id} achievement={a} earned={false} />)}
          </div>
        </div>
      )}

      {/* Install as app (hidden when already standalone) */}
      <InstallPwa />

      {/* Settings */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Settings size={18} className="text-gray-500" />
          <h2 className="font-semibold text-gray-800">Настройки</h2>
        </div>
        <div className="flex flex-col gap-5">
          {/* Language */}
          <div>
            <p className="text-sm text-gray-600 mb-2">Родной язык</p>
            <div className="flex flex-wrap gap-2">
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  onClick={() => setSelectedLang(l.code)}
                  className={`px-3 py-1.5 rounded-lg text-sm border transition-all ${
                    selectedLang === l.code
                      ? 'bg-primary-800 text-white border-primary-800'
                      : 'bg-white text-gray-600 border-gray-200 hover:border-primary-400'
                  }`}
                >
                  {l.label}
                </button>
              ))}
            </div>
            {selectedLang !== (profile?.native_language || 'ru') && (
              <Button className="mt-2 w-full" onClick={handleSaveLang} loading={savingLang}>
                Сохранить язык
              </Button>
            )}
          </div>

          {/* Interest themes */}
          <div>
            <p className="text-sm text-gray-600 mb-2">Интересные темы для заданий</p>
            <div className="grid grid-cols-2 gap-2">
              {INTEREST_THEMES.map((t) => (
                <button
                  key={t.key}
                  onClick={() => toggleTheme(t.key)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 text-xs font-medium text-left transition-all ${
                    selectedThemes.includes(t.key)
                      ? 'border-primary-800 bg-primary-50 text-primary-800'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}
                >
                  <span className="text-base flex-shrink-0">{t.emoji}</span>
                  <span className="leading-tight">{t.key}</span>
                </button>
              ))}
            </div>
            {themesChanged && (
              <Button className="mt-2 w-full" onClick={handleSaveThemes} loading={savingThemes}>
                Сохранить темы
              </Button>
            )}
          </div>
        </div>
      </Card>

      {/* Admin link */}
      {user?.is_admin && (
        <button
          onClick={() => navigate('/admin')}
          className="flex items-center gap-2 text-sm text-gray-400 hover:text-primary-800 transition-colors py-1"
        >
          <ShieldCheck size={16} />
          Панель администратора
        </button>
      )}

      {/* Logout */}
      <button
        onClick={handleLogout}
        className="flex items-center gap-2 text-sm text-red-400 hover:text-red-600 transition-colors py-3"
      >
        <LogOut size={16} />
        Выйти из аккаунта
      </button>
    </div>
  )
}

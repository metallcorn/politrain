import { useEffect, useRef, useState } from 'react'
import Button from '../ui/Button'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, Zap, Flame, Sparkles, Clock, Star } from 'lucide-react'
import { trainingApi, profileApi } from '../../api'
import DailyGoalRing from './DailyGoalRing'

export default function SessionResult({ correct, total, xpEarned, streak, mode, topic, sessionDuration, exerciseIds }) {
  const navigate = useNavigate()
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0

  const [rating, setRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [comment, setComment] = useState('')
  const [ratingSubmitted, setRatingSubmitted] = useState(false)
  // Daily XP goal ring: XP is awarded per answer, so dashboard already includes
  // this session — before = xp_today - xpEarned, no backend change needed
  const [dailyXp, setDailyXp] = useState(null)

  useEffect(() => {
    if (sessionDuration > 0) {
      trainingApi.sessionComplete({ duration_seconds: sessionDuration }).catch(() => {})
    }
    profileApi.dashboard()
      .then((res) => {
        const t = res.data?.today
        if (t?.goal > 0) {
          setDailyXp({
            goal: t.goal,
            after: t.xp_today || 0,
            before: Math.max(0, (t.xp_today || 0) - (xpEarned || 0)),
          })
        }
      })
      .catch(() => {})
  }, [])

  // Ring takes center stage while the goal is being chased; once the norm was
  // already done before this session it moves to a compact spot at the bottom
  const goalWasDoneBefore = dailyXp && dailyXp.before >= dailyXp.goal

  // The star click submits IMMEDIATELY (feedback #117: users didn't notice the send
  // button and ratings were lost). The backend returns rating_id; a later comment (or a
  // changed star) updates the same row via rating_id instead of creating a duplicate.
  const ratingIdRef = useRef(null)

  const sendRating = (stars, text) => {
    trainingApi.sessionRating({
      mode,
      rating: stars || null,
      comment: text || null,
      exercise_ids: exerciseIds || [],
      rating_id: ratingIdRef.current,
    }).then(res => {
      if (res.data?.rating_id) ratingIdRef.current = res.data.rating_id
    }).catch(() => {})
  }

  const handleStarClick = (stars) => {
    setRating(stars)
    sendRating(stars, comment)
  }

  const handleCommentChange = (e) => {
    setComment(e.target.value)
  }

  const handleCommentSubmit = () => {
    sendRating(rating, comment)
    setRatingSubmitted(true)
  }

  const formatDuration = (seconds) => {
    if (!seconds) return null
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    if (m === 0) return `${s} сек`
    return `${m} мин${s > 0 ? ` ${s} сек` : ''}`
  }

  const timeLabel = formatDuration(sessionDuration)

  return (
    <div className="flex flex-col items-center gap-6 py-8 animate-scale-in">
      {dailyXp && !goalWasDoneBefore ? (
        <DailyGoalRing before={dailyXp.before} after={dailyXp.after} goal={dailyXp.goal} />
      ) : (
        <div className="w-20 h-20 rounded-full bg-primary-50 flex items-center justify-center">
          <CheckCircle size={48} className="text-primary-800" />
        </div>
      )}

      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-900">Сессия завершена!</h2>
        <p className="text-gray-500 mt-1">{pct}% правильных ответов</p>
      </div>

      <div className="grid grid-cols-3 gap-4 w-full">
        <div className="card text-center">
          <p className="text-2xl font-bold text-green-600">{correct}</p>
          <p className="text-xs text-gray-500">Правильно</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-red-500">{total - correct}</p>
          <p className="text-xs text-gray-500">Ошибок</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-yellow-500">{total}</p>
          <p className="text-xs text-gray-500">Всего</p>
        </div>
      </div>

      <div className="flex items-center gap-6 flex-wrap justify-center">
        <div className="flex items-center gap-2">
          <Zap className="text-yellow-500" size={20} />
          <span className="font-bold text-gray-800">+{xpEarned} XP</span>
        </div>
        {streak > 0 && (
          <div className="flex items-center gap-2">
            <Flame className="text-orange-500" size={20} />
            <span className="font-bold text-orange-500">{streak} дней</span>
          </div>
        )}
        {timeLabel && (
          <div className="flex items-center gap-2">
            <Clock className="text-blue-400" size={20} />
            <span className="font-bold text-gray-800">{timeLabel}</span>
          </div>
        )}
      </div>

      {/* Daily norm already done before this session — compact ring, second lap fills */}
      {dailyXp && goalWasDoneBefore && (
        <DailyGoalRing before={dailyXp.before} after={dailyXp.after} goal={dailyXp.goal} compact />
      )}

      {/* Session rating */}
      <div className="w-full card flex flex-col items-center gap-2">
        <p className="text-sm text-gray-500">Как прошла сессия?</p>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((star) => (
            <button
              key={star}
              onClick={() => handleStarClick(star)}
              onMouseEnter={() => setHoverRating(star)}
              onMouseLeave={() => setHoverRating(0)}
              className="p-1 transition-transform active:scale-90"
            >
              <Star
                size={28}
                className={`transition-colors ${
                  star <= (hoverRating || rating)
                    ? 'fill-yellow-400 text-yellow-400'
                    : 'text-gray-300'
                }`}
              />
            </button>
          ))}
        </div>
        {rating > 0 && !ratingSubmitted && (
          <div className="w-full flex flex-col gap-2 animate-fade-in">
            <p className="text-xs text-gray-400">Оценка сохранена — можно добавить комментарий</p>
            <textarea
              className="input resize-none h-16 text-sm"
              placeholder="Комментарий (необязательно)..."
              value={comment}
              onChange={handleCommentChange}
              autoFocus
            />
            <button
              onClick={handleCommentSubmit}
              className="text-xs text-primary-700 font-medium self-end"
            >
              Отправить
            </button>
          </div>
        )}
        {ratingSubmitted && (
          <p className="text-xs text-gray-400 animate-fade-in">Спасибо за оценку!</p>
        )}
      </div>

      <div className="flex gap-3 w-full">
        <Button variant="secondary" className="flex-1" onClick={() => navigate('/training')}>
          В меню
        </Button>
        {mode === 'vocab' ? (
          <Button className="flex-1" onClick={() => navigate(`/training/session?mode=vocab&t=${Date.now()}`)}>
            <Sparkles size={16} />
            Ещё слова
          </Button>
        ) : mode === 'topic' && topic ? (
          <Button className="flex-1" onClick={() => navigate(`/training/session?mode=topic&topic=${topic}&t=${Date.now()}`)}>
            <Sparkles size={16} />
            Повторить тему
          </Button>
        ) : mode === 'errors' ? (
          <Button className="flex-1" onClick={() => navigate(`/training/session?mode=errors&t=${Date.now()}`)}>
            <Sparkles size={16} />
            Ещё ошибки
          </Button>
        ) : mode === 'reading' ? (
          <Button className="flex-1" onClick={() => navigate(`/training/session?mode=reading&t=${Date.now()}`)}>
            <Sparkles size={16} />
            Ещё текст
          </Button>
        ) : (
          <Button className="flex-1" onClick={() => navigate(`/training/session?mode=bonus&t=${Date.now()}`)}>
            <Sparkles size={16} />
            Ещё задания
          </Button>
        )}
      </div>
    </div>
  )
}

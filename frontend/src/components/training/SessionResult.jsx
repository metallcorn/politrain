import { useEffect, useRef, useState } from 'react'
import Button from '../ui/Button'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, Zap, Flame, Sparkles, Clock, Star } from 'lucide-react'
import { trainingApi } from '../../api'

export default function SessionResult({ correct, total, xpEarned, streak, mode, topic, sessionDuration, exerciseIds }) {
  const navigate = useNavigate()
  const pct = total > 0 ? Math.round((correct / total) * 100) : 0

  const [rating, setRating] = useState(0)
  const [hoverRating, setHoverRating] = useState(0)
  const [commentOpen, setCommentOpen] = useState(false)
  const [comment, setComment] = useState('')
  const [ratingSubmitted, setRatingSubmitted] = useState(false)
  const autoSubmitTimer = useRef(null)

  useEffect(() => {
    if (sessionDuration > 0) {
      trainingApi.sessionComplete({ duration_seconds: sessionDuration }).catch(() => {})
    }
  }, [])

  const submitRating = (stars, text) => {
    if (ratingSubmitted) return
    clearTimeout(autoSubmitTimer.current)
    setRatingSubmitted(true)
    trainingApi.sessionRating({
      mode,
      rating: stars || null,
      comment: text || null,
      exercise_ids: exerciseIds || [],
    }).catch(() => {})
  }

  const handleStarClick = (stars) => {
    setRating(stars)
    // Auto-submit after 2s — cancelled if user opens comment box first
    clearTimeout(autoSubmitTimer.current)
    autoSubmitTimer.current = setTimeout(() => submitRating(stars, ''), 2000)
  }

  const handleCommentOpen = () => {
    clearTimeout(autoSubmitTimer.current)
    setCommentOpen(true)
  }

  const handleCommentSubmit = () => {
    submitRating(rating, comment)
    setCommentOpen(false)
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
      <div className="w-20 h-20 rounded-full bg-primary-50 flex items-center justify-center">
        <CheckCircle size={48} className="text-primary-800" />
      </div>

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
        {rating > 0 && !commentOpen && !ratingSubmitted && (
          <button
            onClick={handleCommentOpen}
            className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
          >
            + оставить комментарий
          </button>
        )}
        {commentOpen && (
          <div className="w-full flex flex-col gap-2 animate-fade-in">
            <textarea
              className="input resize-none h-16 text-sm"
              placeholder="Что понравилось или не понравилось?"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
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
        {ratingSubmitted && !commentOpen && rating > 0 && (
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

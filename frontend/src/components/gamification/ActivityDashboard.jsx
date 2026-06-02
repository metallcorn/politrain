import { useState } from 'react'
import { Flame, Clock, Zap, Trophy } from 'lucide-react'

function formatTime(seconds) {
  if (!seconds) return '0 мин'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h === 0) return `${m} мин`
  if (m === 0) return `${h} ч`
  return `${h} ч ${m} мин`
}

function Ring({ done, goal }) {
  const pct = goal > 0 ? Math.min(done / goal, 1) : 0
  const r = 44
  const circ = 2 * Math.PI * r
  const dash = pct * circ
  const displayPct = Math.round(pct * 100)

  return (
    <svg width="110" height="110" viewBox="0 0 110 110" className="flex-shrink-0">
      <circle cx="55" cy="55" r={r} fill="none" stroke="#f3f4f6" strokeWidth="10" />
      <circle
        cx="55" cy="55" r={r} fill="none"
        stroke={pct >= 1 ? '#22c55e' : '#6366f1'}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={`${dash} ${circ}`}
        strokeDashoffset="0"
        transform="rotate(-90 55 55)"
        style={{ transition: 'stroke-dasharray 0.6s ease' }}
      />
      <text x="55" y="50" textAnchor="middle" className="text-xs" fontSize="18" fontWeight="bold" fill="#111827">
        {displayPct}%
      </text>
      <text x="55" y="67" textAnchor="middle" fontSize="11" fill="#6b7280">
        цели
      </text>
    </svg>
  )
}

function WeekChart({ week, metric }) {
  const values = week.map(d => metric === 'xp' ? (d.xp || 0) : d.exercises)
  const max = Math.max(...values, 1)
  return (
    <div className="flex items-end gap-1 h-16">
      {week.map((d, i) => {
        const val = values[i]
        const h = max > 0 ? Math.max((val / max) * 100, val > 0 ? 8 : 0) : 0
        return (
          <div key={d.date} className="flex-1 flex flex-col items-center gap-1">
            <div className="w-full flex items-end justify-center" style={{ height: 44 }}>
              <div
                className={`w-full rounded-t-sm transition-all duration-500 ${
                  d.is_today
                    ? 'bg-primary-500'
                    : val > 0
                    ? 'bg-primary-200'
                    : 'bg-gray-100'
                }`}
                style={{ height: `${h}%` }}
              />
            </div>
            <span className={`text-[10px] ${d.is_today ? 'text-primary-600 font-semibold' : 'text-gray-400'}`}>
              {d.day}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function MonthChart({ month, metric }) {
  const values = month.map(d => metric === 'xp' ? (d.xp || 0) : d.exercises)
  const max = Math.max(...values, 1)
  return (
    <div className="flex items-end gap-px h-8">
      {month.map((d, i) => {
        const val = values[i]
        const h = max > 0 ? Math.max((val / max) * 100, val > 0 ? 15 : 0) : 0
        return (
          <div
            key={d.date}
            className={`flex-1 rounded-sm ${val > 0 ? 'bg-primary-300' : 'bg-gray-100'}`}
            style={{ height: `${h}%` }}
            title={`${d.date}: ${val} ${metric === 'xp' ? 'XP' : 'заданий'}`}
          />
        )
      })}
    </div>
  )
}

function SourceBar({ label, pct, colorClass }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500 w-24 flex-shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${colorClass}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

const SOURCE_COLORS = {
  'Дневная':    'bg-primary-500',
  'Бонус':      'bg-purple-400',
  'Словарь':    'bg-blue-400',
  'Темы':       'bg-teal-400',
  'Повторение': 'bg-orange-400',
}

export default function ActivityDashboard({ data }) {
  const [metric, setMetric] = useState('exercises')

  if (!data) return null

  const { today, week, month, by_source, totals } = data
  const accuracy = today.exercises > 0
    ? Math.round((today.correct / today.exercises) * 100)
    : null

  const weekTotal = week.reduce((s, d) => s + (metric === 'xp' ? (d.xp || 0) : d.exercises), 0)
  const monthTotal = month.reduce((s, d) => s + (metric === 'xp' ? (d.xp || 0) : d.exercises), 0)

  const bestStreak = totals.best_streak || 0

  return (
    <div className="flex flex-col gap-4">
      {/* Top stats chips */}
      <div className="grid grid-cols-2 gap-2">
        <div className="card text-center py-3">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Flame size={14} className="text-orange-500" />
            <span className="font-bold text-gray-900">{totals.streak_days}</span>
          </div>
          <p className="text-[11px] text-gray-400">дней подряд</p>
          {bestStreak > 0 && (
            <p className="text-[10px] text-gray-300 mt-0.5">рекорд: {bestStreak}</p>
          )}
        </div>
        <div className="card text-center py-3">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Clock size={14} className="text-blue-500" />
            <span className="font-bold text-gray-900">{formatTime(totals.total_time_seconds)}</span>
          </div>
          <p className="text-[11px] text-gray-400">всего времени</p>
        </div>
        <div className="card text-center py-3">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Zap size={14} className="text-yellow-500" />
            <span className="font-bold text-gray-900">{totals.xp}</span>
          </div>
          <p className="text-[11px] text-gray-400">XP набрано</p>
        </div>
        <div className="card text-center py-3">
          <div className="flex items-center justify-center gap-1 mb-0.5">
            <Trophy size={14} className="text-amber-500" />
            <span className="font-bold text-gray-900">{today.xp_today || 0}</span>
          </div>
          <p className="text-[11px] text-gray-400">XP сегодня</p>
        </div>
      </div>

      {/* Today */}
      <div className="card">
        <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">Сегодня</p>
        <div className="flex items-center gap-4">
          <Ring done={today.exercises} goal={today.goal} />
          <div className="flex flex-col gap-2 flex-1">
            <div>
              <p className="text-2xl font-bold text-gray-900 leading-none">
                {today.exercises}
                <span className="text-sm font-normal text-gray-400"> / {today.goal}</span>
              </p>
              <p className="text-xs text-gray-400 mt-0.5">заданий выполнено</p>
            </div>
            {accuracy !== null && (
              <div>
                <p className="text-lg font-bold text-green-600 leading-none">{accuracy}%</p>
                <p className="text-xs text-gray-400 mt-0.5">правильных ответов</p>
              </div>
            )}
            {today.minutes > 0 && (
              <div>
                <p className="text-lg font-bold text-blue-500 leading-none">{today.minutes} мин</p>
                <p className="text-xs text-gray-400 mt-0.5">времени занятий</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Week */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Эта неделя</p>
          <div className="flex items-center gap-2">
            <p className="text-xs font-semibold text-gray-600">
              {weekTotal} {metric === 'xp' ? 'XP' : 'заданий'}
            </p>
            <button
              onClick={() => setMetric(m => m === 'exercises' ? 'xp' : 'exercises')}
              className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 hover:bg-gray-200 transition-colors"
            >
              {metric === 'exercises' ? 'XP' : 'задания'}
            </button>
          </div>
        </div>
        <WeekChart week={week} metric={metric} />
      </div>

      {/* Month */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-gray-400 uppercase tracking-wide">30 дней</p>
          <p className="text-xs font-semibold text-gray-600">
            {monthTotal} {metric === 'xp' ? 'XP' : 'заданий'}
          </p>
        </div>
        <MonthChart month={month} metric={metric} />
        <div className="flex justify-between mt-1.5">
          <span className="text-[10px] text-gray-300">{month[0]?.date?.slice(5)}</span>
          <span className="text-[10px] text-gray-300">сегодня</span>
        </div>
      </div>

      {/* By source */}
      {by_source.length > 0 && (
        <div className="card">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">По режиму (30 дней)</p>
          <div className="flex flex-col gap-2">
            {by_source.map((s) => (
              <SourceBar
                key={s.key}
                label={s.label}
                pct={s.pct}
                colorClass={SOURCE_COLORS[s.label] || 'bg-gray-400'}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

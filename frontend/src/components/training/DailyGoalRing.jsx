import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'

// Animated daily XP goal ring for the session-complete screen.
// Fills from pre-session XP to post-session XP so the user sees how much
// this session moved them toward the daily goal. When the goal is crossed
// for the first time today — confetti. When the goal was already done before
// the session, the ring renders compact and fills a second "lap" layer on top.
//
// before/after — daily XP before and after this session; goal — daily XP goal.

const CONFETTI_COLORS = ['#f59e0b', '#ef4444', '#3b82f6', '#22c55e', '#a855f7', '#ec4899']

function ConfettiBurst() {
  const particles = useMemo(
    () =>
      Array.from({ length: 36 }, (_, i) => ({
        id: i,
        x: (Math.random() - 0.5) * 280,
        y: -(60 + Math.random() * 200),
        rotate: (Math.random() - 0.5) * 540,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        delay: Math.random() * 0.25,
        size: 6 + Math.random() * 6,
      })),
    []
  )
  return (
    <div className="absolute inset-0 pointer-events-none overflow-visible flex items-center justify-center">
      {particles.map((p) => (
        <motion.span
          key={p.id}
          className="absolute rounded-sm"
          style={{ width: p.size, height: p.size * 0.6, backgroundColor: p.color }}
          initial={{ x: 0, y: 0, opacity: 1, rotate: 0, scale: 1 }}
          animate={{ x: p.x, y: [0, p.y, p.y + 320], opacity: [1, 1, 0], rotate: p.rotate }}
          transition={{ duration: 1.8, delay: p.delay, ease: 'easeOut', times: [0, 0.45, 1] }}
        />
      ))}
    </div>
  )
}

export default function DailyGoalRing({ before, after, goal, compact = false }) {
  const size = compact ? 96 : 150
  const stroke = compact ? 8 : 11
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r

  // Lap = how many times the goal is already fully filled before this session.
  // Within the current lap the ring animates from `from` to `to` fraction.
  const lap = goal > 0 ? Math.floor(before / goal) : 0
  const from = goal > 0 ? Math.min((before - lap * goal) / goal, 1) : 0
  const rawTo = goal > 0 ? (after - lap * goal) / goal : 0
  const to = Math.min(Math.max(rawTo, from), 1) // cap at full lap; crossing fires confetti
  const crossed = goal > 0 && before < goal && after >= goal

  const [fill, setFill] = useState(from)
  const [celebrate, setCelebrate] = useState(false)

  useEffect(() => {
    // start from `from`, then animate to `to` on the next frame (CSS transition does the work)
    const t = setTimeout(() => {
      setFill(to)
      if (crossed) setTimeout(() => setCelebrate(true), 900)
    }, 350)
    return () => clearTimeout(t)
  }, [to, crossed])

  const done = after >= goal
  const arcColor = done ? '#22c55e' : '#1e40af'
  // base circle: gray while filling the first lap, soft green once a full lap is underneath
  const baseColor = lap >= 1 || done ? '#bbf7d0' : '#e5e7eb'

  return (
    <div className="relative flex flex-col items-center" style={{ width: size }}>
      {celebrate && <ConfettiBurst />}
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={baseColor} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={arcColor}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - fill)}
          style={{ transition: 'stroke-dashoffset 1.1s ease-out, stroke 0.4s' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center -mt-1">
        <span className={`font-bold text-gray-900 ${compact ? 'text-sm' : 'text-xl'}`}>
          {after}
          <span className={`font-normal text-gray-400 ${compact ? 'text-xs' : 'text-sm'}`}> / {goal}</span>
        </span>
        <span className={`text-gray-400 ${compact ? 'text-[10px]' : 'text-xs'}`}>
          {lap >= 1 ? `XP · цель ×${lap + 1}` : 'XP за день'}
        </span>
      </div>
      {!compact && done && (
        <p className="mt-1 text-sm font-medium text-green-600 animate-fade-in">Дневная цель выполнена! 🎉</p>
      )}
      {!compact && !done && goal > after && (
        <p className="mt-1 text-xs text-gray-400">ещё {goal - after} XP до цели</p>
      )}
    </div>
  )
}

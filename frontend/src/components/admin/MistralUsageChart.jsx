import { useEffect, useState } from 'react'
import { adminApi } from '../../api'
import Skeleton from '../ui/Skeleton'

const MODEL_COLORS = {
  'mistral-large-latest': '#6366f1',
  'mistral-small-latest': '#22c55e',
}
const MODEL_LABELS = {
  'mistral-large-latest': 'Large',
  'mistral-small-latest': 'Small',
}

function formatCost(usd) {
  if (usd < 0.001) return `$${(usd * 1000).toFixed(3)}m`
  return `$${usd.toFixed(4)}`
}

function formatTokens(n) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(0)}k`
  return String(n)
}

function DayChart({ days }) {
  const models = ['mistral-large-latest', 'mistral-small-latest']
  const maxCalls = Math.max(
    ...days.map(d => models.reduce((s, m) => s + (d.models[m]?.calls || 0), 0)),
    1
  )

  return (
    <div>
      <div className="flex items-end gap-px" style={{ height: 80 }}>
        {days.map((d) => {
          const total = models.reduce((s, m) => s + (d.models[m]?.calls || 0), 0)
          const h = Math.max((total / maxCalls) * 100, total > 0 ? 4 : 0)
          const largePct = total > 0
            ? ((d.models['mistral-large-latest']?.calls || 0) / total) * 100
            : 0
          return (
            <div
              key={d.date}
              className="flex-1 flex flex-col justify-end overflow-hidden rounded-sm"
              style={{ height: `${h}%` }}
              title={`${d.date}: ${total} вызовов`}
            >
              <div style={{ height: `${largePct}%`, background: MODEL_COLORS['mistral-large-latest'] }} />
              <div style={{ height: `${100 - largePct}%`, background: MODEL_COLORS['mistral-small-latest'] }} />
            </div>
          )
        })}
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-gray-300">{days[0]?.date?.slice(5)}</span>
        <span className="text-[10px] text-gray-300">сегодня</span>
      </div>
    </div>
  )
}

export default function MistralUsageChart() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [period, setPeriod] = useState(30)
  const [pool, setPool] = useState(null)

  useEffect(() => {
    setLoading(true)
    Promise.allSettled([
      adminApi.mistralUsage(period),
      adminApi.poolStats(),
    ]).then(([usageRes, poolRes]) => {
      if (usageRes.status === 'fulfilled') setData(usageRes.value.data)
      if (poolRes.status === 'fulfilled') setPool(poolRes.value.data)
    }).finally(() => setLoading(false))
  }, [period])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-gray-800">Использование Mistral API</h2>
        <div className="flex gap-1">
          {[7, 30, 90].map(d => (
            <button
              key={d}
              onClick={() => setPeriod(d)}
              className={`text-xs px-2 py-1 rounded-lg transition-colors ${
                period === d ? 'bg-primary-100 text-primary-700 font-medium' : 'text-gray-400 hover:text-gray-600'
              }`}
            >
              {d}д
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-16 rounded-2xl" />
          <Skeleton className="h-20 rounded-2xl" />
        </div>
      ) : !data ? (
        <p className="text-sm text-gray-400">Нет данных</p>
      ) : (
        <>
          {/* Totals */}
          <div className="grid grid-cols-2 gap-2">
            <div className="card py-3">
              <p className="text-xl font-bold text-gray-900">{data.totals.calls}</p>
              <p className="text-xs text-gray-400">вызовов API</p>
            </div>
            <div className="card py-3">
              <p className="text-xl font-bold text-primary-700">${data.totals.cost_usd.toFixed(3)}</p>
              <p className="text-xs text-gray-400">расходы (USD)</p>
            </div>
            <div className="card py-3">
              <p className="text-xl font-bold text-gray-900">{formatTokens(data.totals.input_tokens)}</p>
              <p className="text-xs text-gray-400">входных токенов</p>
            </div>
            <div className="card py-3">
              <p className="text-xl font-bold text-gray-900">{formatTokens(data.totals.output_tokens)}</p>
              <p className="text-xs text-gray-400">выходных токенов</p>
            </div>
          </div>

          {/* Exercise pool stats */}
          {pool && (
            <div className="card">
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">Пул упражнений</p>
              <div className="grid grid-cols-3 gap-2 mb-3">
                <div className="text-center">
                  <p className="text-lg font-bold text-gray-900">{pool.total}</p>
                  <p className="text-[10px] text-gray-400">всего</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold text-green-600">{pool.active}</p>
                  <p className="text-[10px] text-gray-400">активных</p>
                </div>
                <div className="text-center">
                  <p className="text-lg font-bold text-red-400">{pool.inactive}</p>
                  <p className="text-[10px] text-gray-400">отключено</p>
                </div>
              </div>
              {Object.keys(pool.by_type || {}).length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {Object.entries(pool.by_type).sort((a, b) => b[1] - a[1]).map(([type, count]) => (
                    <span key={type} className="text-[10px] bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                      {type} {count}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Legend */}
          <div className="flex gap-4">
            {Object.entries(MODEL_LABELS).map(([model, label]) => (
              <div key={model} className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded-sm flex-shrink-0" style={{ background: MODEL_COLORS[model] }} />
                <span className="text-xs text-gray-500">{label}</span>
              </div>
            ))}
          </div>

          {/* Day chart */}
          <div className="card">
            <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">Вызовы по дням</p>
            <DayChart days={data.days} />
          </div>

          {/* By purpose */}
          {data.by_purpose.length > 0 && (
            <div className="card">
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">По назначению</p>
              <div className="flex flex-col gap-2">
                {data.by_purpose.map(p => {
                  const maxCalls = data.by_purpose[0].calls
                  return (
                    <div key={p.purpose} className="flex items-center gap-2">
                      <span className="text-xs text-gray-500 w-28 flex-shrink-0 truncate">{p.purpose}</span>
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary-400 rounded-full"
                          style={{ width: `${(p.calls / maxCalls) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 w-10 text-right flex-shrink-0">{p.calls}</span>
                      <span className="text-xs text-gray-400 w-14 text-right flex-shrink-0">{formatCost(p.cost)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* By user */}
          {data.by_user.length > 0 && (
            <div className="card">
              <p className="text-xs text-gray-400 uppercase tracking-wide mb-3">По пользователям</p>
              <div className="flex flex-col gap-2">
                {data.by_user.map(u => (
                  <div key={u.user_id} className="flex items-center justify-between text-sm">
                    <span className="text-gray-700 font-medium">{u.username}</span>
                    <div className="flex gap-3 text-xs text-gray-400">
                      <span>{u.calls} вызовов</span>
                      <span>{formatTokens(u.input_tokens + u.output_tokens)} токенов</span>
                      <span className="text-primary-600 font-medium">{formatCost(u.cost)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { adminApi, errorMessage } from '../../api'
import Button from '../ui/Button'
import Input from '../ui/Input'
import Spinner from '../ui/Spinner'
import MistralUsageChart from './MistralUsageChart'

const KEY_LABEL = {
  ok: { text: 'Ключ работает', color: 'text-green-700 bg-green-50 border-green-200', dot: 'bg-green-500' },
  unauthorized: { text: 'Ключ отклонён (401) — обнови', color: 'text-red-700 bg-red-50 border-red-200', dot: 'bg-red-500' },
  missing: { text: 'Ключ не задан', color: 'text-red-700 bg-red-50 border-red-200', dot: 'bg-red-500' },
}

export default function SystemHealth() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [newKey, setNewKey] = useState('')
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState(null)

  const load = () => {
    setLoading(true)
    adminApi.system().then((r) => setData(r.data)).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const saveKey = async () => {
    setSaving(true); setMsg(null)
    try {
      const r = await adminApi.setMistralKey(newKey.trim())
      setMsg({ ok: true, text: `Ключ обновлён (…${r.data.tail}) и проверен` })
      setNewKey('')
      load()
    } catch (e) {
      setMsg({ ok: false, text: errorMessage(e, 'Не удалось сохранить ключ') })
    } finally {
      setSaving(false)
    }
  }

  if (loading || !data) return <div className="flex justify-center py-8"><Spinner /></div>

  const ks = KEY_LABEL[data.key.status] || {
    text: `Статус: ${data.key.status}`, color: 'text-orange-700 bg-orange-50 border-orange-200', dot: 'bg-orange-500',
  }

  return (
    <div className="flex flex-col gap-5">
      {/* Key status + updater */}
      <div className={`rounded-xl border px-4 py-3 ${ks.color}`}>
        <div className="flex items-center gap-2 font-medium">
          <span className={`w-2.5 h-2.5 rounded-full ${ks.dot}`} />
          Mistral: {ks.text}
        </div>
        <p className="text-xs mt-1 opacity-80">
          Ключ …{data.key.tail || '—'} · источник: {data.key.source}
        </p>
      </div>

      <div className="card flex flex-col gap-2">
        <p className="font-medium text-gray-800 text-sm">Обновить ключ Mistral</p>
        <p className="text-xs text-gray-500">Вставь новый ключ — он проверится и сохранится без перезапуска. Взять: console.mistral.ai/api-keys</p>
        <Input placeholder="Новый API-ключ..." value={newKey} onChange={(e) => setNewKey(e.target.value)} />
        <Button onClick={saveKey} loading={saving} disabled={newKey.trim().length < 20} className="self-start">
          Проверить и сохранить
        </Button>
        {msg && <p className={`text-sm ${msg.ok ? 'text-green-600' : 'text-red-600'}`}>{msg.text}</p>}
      </div>

      {/* Health cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card text-center py-3">
          <p className="text-xl font-bold text-green-600">{data.mistral_24h.ok}</p>
          <p className="text-xs text-gray-500">Успешных вызовов (24ч)</p>
        </div>
        <div className="card text-center py-3">
          <p className={`text-xl font-bold ${data.mistral_24h.failed > 0 ? 'text-red-500' : 'text-gray-400'}`}>{data.mistral_24h.failed}</p>
          <p className="text-xs text-gray-500">Сбоев (24ч)</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-xl font-bold text-primary-800">{data.pool.active}</p>
          <p className="text-xs text-gray-500">Активных в пуле</p>
        </div>
        <div className="card text-center py-3">
          <p className="text-xl font-bold text-gray-700">{data.db_mb}</p>
          <p className="text-xs text-gray-500">Размер БД, МБ</p>
        </div>
      </div>

      {/* Spend graphs */}
      <div>
        <h3 className="font-semibold text-gray-800 mb-2">Расход Mistral</h3>
        <MistralUsageChart />
      </div>
    </div>
  )
}

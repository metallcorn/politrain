import { useState } from 'react'
import { Gift, X, Sparkles } from 'lucide-react'

// «Что нового» — changelog panel. Add an entry to the TOP of CHANGELOG when shipping a
// user-facing feature. `id` must be a monotonically increasing string; the highest id the
// user has opened is stored in localStorage, and a red dot shows while unseen ids exist.
const CHANGELOG = [
  {
    id: '2026-07-29',
    title: 'Тянем до B1 и выше',
    items: [
      'Словарь больше не застревает — новые слова подтягиваются на уровень выше твоего.',
      'Добавили 6 новых грамматических тем B1: относительные придаточные, союзы, приставки и вид глагола, безличные конструкции, степени наречий, косвенная речь.',
      'Задания теперь в контексте твоих интересов (банк, аэропорт, работа), а не «на столе лежит яблоко».',
      'Трудные темы уровня выше стали выпадать чаще — меньше топтания на месте.',
      'Шкала прогресса до B1 стала честной: двигается, когда ты улучшаешь любую тему, а не только при полном освоении.',
    ],
  },
  {
    id: '2026-07-25',
    title: 'Повторение по-умному',
    items: [
      'Хорошо выученное перестаёт мозолить глаза: если ответил верно после долгого перерыва — тема уходит из повторения.',
      'Очередь повторений больше не растёт бесконечно.',
      'Кнопка «Переобъяснить заново» — если объяснение не про твою ошибку.',
    ],
  },
  {
    id: '2026-07-17',
    title: 'Приложение на телефон',
    items: [
      'В профиле — кнопка «Установить как приложение»: иконка на домашнем экране, работает как обычное приложение.',
      'Перевод по клику на ЛЮБОЕ слово в задании, а не только подчёркнутые.',
    ],
  },
]

const LS_KEY = 'whatsnew_seen'

export default function WhatsNew() {
  const [open, setOpen] = useState(false)
  const latestId = CHANGELOG[0]?.id || ''
  const seenId = (typeof localStorage !== 'undefined' && localStorage.getItem(LS_KEY)) || ''
  const [hasUnseen, setHasUnseen] = useState(seenId < latestId)

  const handleOpen = () => {
    setOpen(true)
    setHasUnseen(false)
    try { localStorage.setItem(LS_KEY, latestId) } catch { /* ignore */ }
  }

  return (
    <>
      <button
        onClick={handleOpen}
        title="Что нового"
        className="relative text-gray-400 hover:text-primary-700 transition-colors"
      >
        <Gift size={20} />
        {hasUnseen && (
          <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-red-500 rounded-full ring-2 ring-white" />
        )}
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center p-4"
             onClick={() => setOpen(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md p-5 max-h-[80vh] overflow-y-auto animate-scale-in"
               onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                <Sparkles size={18} className="text-primary-600" />
                Что нового
              </h3>
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <div className="flex flex-col gap-5">
              {CHANGELOG.map((entry) => (
                <div key={entry.id}>
                  <div className="flex items-baseline gap-2 mb-1.5">
                    <span className="font-medium text-gray-800 text-sm">{entry.title}</span>
                    <span className="text-xs text-gray-400">{entry.id}</span>
                  </div>
                  <ul className="flex flex-col gap-1.5">
                    {entry.items.map((it, i) => (
                      <li key={i} className="text-sm text-gray-600 flex gap-2">
                        <span className="text-primary-400 flex-shrink-0">•</span>
                        <span>{it}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

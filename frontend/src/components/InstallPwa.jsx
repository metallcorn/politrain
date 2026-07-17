import { useEffect, useState } from 'react'
import { Share, PlusSquare, Smartphone, X } from 'lucide-react'
import Card from './ui/Card'
import Button from './ui/Button'

// «Установить приложение» in the profile. iOS has NO install API — Safari only allows
// Share → «На экран „Домой“», so we show an illustrated walkthrough. On Android/Chrome
// we capture beforeinstallprompt and trigger the real install dialog. Hidden entirely
// when already running as an installed app (standalone).
let deferredPrompt = null
if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferredPrompt = e
  })
}

const isStandalone = () =>
  window.matchMedia?.('(display-mode: standalone)')?.matches || window.navigator.standalone === true

const isIOS = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent)

export default function InstallPwa() {
  const [showGuide, setShowGuide] = useState(false)
  const [installed, setInstalled] = useState(isStandalone())

  useEffect(() => {
    const onInstalled = () => setInstalled(true)
    window.addEventListener('appinstalled', onInstalled)
    return () => window.removeEventListener('appinstalled', onInstalled)
  }, [])

  if (installed) return null

  const handleClick = async () => {
    if (!isIOS() && deferredPrompt) {
      deferredPrompt.prompt()
      const choice = await deferredPrompt.userChoice.catch(() => null)
      if (choice?.outcome === 'accepted') setInstalled(true)
      deferredPrompt = null
      return
    }
    setShowGuide(true) // iOS or no prompt available — show the walkthrough
  }

  return (
    <>
      <Card className="flex items-center gap-3">
        <Smartphone size={22} className="text-primary-700 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-800 text-sm">Установи как приложение</p>
          <p className="text-xs text-gray-400">Иконка на экране, работает как обычное приложение</p>
        </div>
        <Button variant="secondary" onClick={handleClick} className="!py-2 !px-3 text-sm flex-shrink-0">
          Установить
        </Button>
      </Card>

      {showGuide && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center p-4"
          onClick={() => setShowGuide(false)}
        >
          <div
            className="bg-white rounded-2xl p-5 w-full max-w-sm animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-gray-800">Как установить на iPhone</h3>
              <button onClick={() => setShowGuide(false)} className="text-gray-400 hover:text-gray-600">
                <X size={20} />
              </button>
            </div>
            <ol className="flex flex-col gap-4 text-sm text-gray-700">
              <li className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary-50 text-primary-800 font-semibold flex items-center justify-center flex-shrink-0">1</span>
                <span className="flex items-center gap-1.5 flex-wrap">
                  Открой сайт в <b>Safari</b> и нажми кнопку «Поделиться»
                  <Share size={18} className="text-blue-500 inline" />
                  внизу экрана
                </span>
              </li>
              <li className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary-50 text-primary-800 font-semibold flex items-center justify-center flex-shrink-0">2</span>
                <span className="flex items-center gap-1.5 flex-wrap">
                  Пролистай вниз и выбери
                  <b className="inline-flex items-center gap-1">«На экран „Домой“» <PlusSquare size={16} /></b>
                </span>
              </li>
              <li className="flex items-start gap-3">
                <span className="w-6 h-6 rounded-full bg-primary-50 text-primary-800 font-semibold flex items-center justify-center flex-shrink-0">3</span>
                <span>Нажми <b>«Добавить»</b> — иконка Politrain появится на домашнем экране 🐸</span>
              </li>
            </ol>
            <p className="text-xs text-gray-400 mt-4">
              Важно: из Chrome или встроенного браузера Telegram установка не работает — только Safari.
            </p>
          </div>
        </div>
      )}
    </>
  )
}

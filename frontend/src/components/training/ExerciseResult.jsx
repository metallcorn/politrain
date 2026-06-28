import Markdown from '../ui/Markdown'

// Highlight the part of the correct answer that differs from what the user typed,
// so the actual mistake (often just an ending) jumps out (feedback #95). Compares
// word-by-word; within a differing word, bolds the diverging tail. Falls back to
// bolding the whole answer when there's no usable user answer.
function HighlightedAnswer({ answer, userAnswer }) {
  if (!answer) return null
  if (!userAnswer || typeof userAnswer !== 'string') return <strong>{answer}</strong>
  const aw = answer.split(/(\s+)/)
  const uw = userAnswer.trim().split(/\s+/)
  let wi = 0
  return (
    <strong>
      {aw.map((tok, i) => {
        if (/^\s+$/.test(tok)) return tok
        const u = (uw[wi] || '').toLowerCase().replace(/[.,!?;:]/g, '')
        const a = tok.toLowerCase().replace(/[.,!?;:]/g, '')
        wi++
        if (u === a) return <span key={i} className="font-normal text-gray-500">{tok}</span>
        // find shared prefix length, bold the diverging tail
        let p = 0
        while (p < tok.length && p < u.length && tok[p].toLowerCase() === u[p]) p++
        return (
          <span key={i}>
            <span className="font-normal text-gray-500">{tok.slice(0, p)}</span>
            <span className="text-red-700 underline decoration-2">{tok.slice(p)}</span>
          </span>
        )
      })}
    </strong>
  )
}

// Shared result-feedback card for exercise types.
// Keeps the green/red ✓/✗ block visually identical everywhere.
//
// Props:
//   result            — { is_correct, correct_answer, explanation, xp_earned, diacritic_hint }
//   hintUsed          — show "(с подсказкой)" suffix when answered correctly with a hint
//   showCorrectAnswer — render the correct answer line on wrong answers (default true).
//                       Pass false for judge_sentence (the true/false choice already shows it).
//   variants          — array of alternative correct answers (order_words); renders "Варианты: •…"
//   translation       — optional sentence translation shown italic-gray under the verdict
//   userAnswer        — what the user typed; used to highlight the differing part (#95)
export default function ExerciseResult({
  result,
  hintUsed = false,
  showCorrectAnswer = true,
  variants = null,
  translation = null,
  userAnswer = null,
}) {
  if (!result) return null
  const correct = result.is_correct

  return (
    <div className={`rounded-xl p-4 animate-bounce-in ${correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
      <p className={`font-semibold ${correct ? 'text-green-700' : 'text-red-700'}`}>
        {correct
          ? result.diacritic_hint ? '✓ Верно, но...' : '✓ Правильно!'
          : '✗ Неправильно'}
        {hintUsed && correct && <span className="font-normal text-sm ml-2">(с подсказкой)</span>}
      </p>

      {result.diacritic_hint && (
        <p className="text-sm text-amber-700 mt-1">
          Не забывайте про диакритические знаки: <strong>{result.correct_answer}</strong>
        </p>
      )}

      {!correct && showCorrectAnswer && (
        variants && variants.length > 1
          ? <div className="text-sm text-gray-700 mt-1">
              <span>Варианты:</span>
              {variants.map((a, i) => <p key={i} className="font-medium ml-2">• {a}</p>)}
            </div>
          : result.correct_answer && (
              <p className="text-sm text-gray-700 mt-1">
                Правильный ответ: <HighlightedAnswer answer={result.correct_answer} userAnswer={userAnswer} />
              </p>
            )
      )}

      {translation && <p className="text-sm text-gray-500 mt-1 italic">{translation}</p>}
      {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
      {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
    </div>
  )
}

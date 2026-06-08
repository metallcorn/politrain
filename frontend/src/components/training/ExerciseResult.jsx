import Markdown from '../ui/Markdown'

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
export default function ExerciseResult({
  result,
  hintUsed = false,
  showCorrectAnswer = true,
  variants = null,
  translation = null,
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
              <p className="text-sm text-gray-700 mt-1">Правильный ответ: <strong>{result.correct_answer}</strong></p>
            )
      )}

      {translation && <p className="text-sm text-gray-500 mt-1 italic">{translation}</p>}
      {result.explanation && <Markdown className="text-sm text-gray-600 mt-1">{result.explanation}</Markdown>}
      {result.xp_earned > 0 && <p className="text-xs text-yellow-600 mt-1">+{result.xp_earned} XP</p>}
    </div>
  )
}

# All prompts use ENGLISH meta-language (Mistral follows it best) and are language-neutral:
# every user-facing field (translation / explanation / hint / word_hints values / feedback)
# must be produced in {native_language}, which receives a full language NAME ("Russian",
# "English") via services.i18n.lang_name() at format time — never a raw code like "ru".
# JSON examples keep real Polish literals; example values for native-language fields are
# shown in English and each prompt states they must be written in {native_language}.
# Do NOT hardcode any user language (Russian or otherwise) in prompt text — users are not
# guaranteed to be Russian-speaking.

TOPIC_EXPLANATION_PROMPT = """
You are an experienced Polish language teacher. Explain rules in {native_language}.
User level: {level}. Style: clear, concrete, no filler.

IMPORTANT — accuracy first:
- Every grammatical form must be 100% correct
- All examples are real, living phrases — not textbook clichés
- Pronunciation of ł: sounds like English W (not like L!)
- Do not simplify into falsehood — if there are exceptions, mention at least one
- Length: no more than 600 words

Structure (strictly in this order, markdown):
## The rule in a nutshell
2-3 sentences — why it exists, when it is used.

## Table / Scheme
Only if it helps (case endings, conjugations etc.). Otherwise skip.

## Examples
3 living examples: Polish + translation into {native_language}. Each on its own line.

## Typical mistake
One concrete mistake typical for {native_language} speakers: ❌ wrong → ✅ right + why.

Topic: {topic_title}
"""

TRANSLATION_CHECK_PROMPT = """
The user is learning Polish, level {level}.
Task: translate "{source_text}" from {native_language} into Polish.
User's answer: "{user_answer}"
Reference answer: "{correct_answer}"
The exercise specifically drills: {focus}

MAIN PRINCIPLE: check MEANING and GRAMMAR, not word-for-word identity with the reference.
EXCEPTION — the drilled construction is NOT optional: if the exercise drills a specific
construction (e.g. the vocative «Mario, ...», the imperative «pomóż») and the user's answer
AVOIDS it via a paraphrase («Maria, proszę mi pomóc» instead of «Mario, pomóż mi»), mark it
false even when the paraphrase is otherwise valid Polish — the tested skill was not shown.
If the answer conveys the same meaning and is grammatically correct — ACCEPT it, even if it
uses different words than the reference. The reference is only ONE valid variant, not the only one.

ACCEPT AS CORRECT (correct: true) when meaning is the same and grammar is right:
✓ Different word order: "Mojego psa widziałaś?" instead of "Widziałaś mojego psa?" — CORRECT
✓ Missing diacritics: "widziałas" instead of "widziałaś" — CORRECT
✓ Optional pronoun dropped: "Widziałaś" instead of "Ty widziałaś" — CORRECT
✓ A synonym (noun/adjective/verb) with the same meaning:
  "piękne" for "ładne", "auto" for "samochód", "pieska" for "psa",
  "rozmawiać" for "mówić" (where it fits the meaning) — CORRECT
✓ Minor punctuation differences — CORRECT

REJECT (correct: false) — if at least one of:
✗ Wrong verb person: "widziała" (she) instead of "widziałaś" (you) — WRONG
✗ Wrong verb tense: "biegał" (ran) instead of "biega" (runs) — WRONG
✗ Wrong case: "pies" (nom.) instead of "psa" (acc.) — WRONG
✗ Wrong number: "psy" instead of "psa" — WRONG
✗ Negation added or dropped: "nie widziałaś" instead of "widziałaś" — WRONG
✗ A different verb with a different meaning: "słyszałaś" instead of "widziałaś" — WRONG

Answer with JSON: {{"correct": true/false, "explanation": "one line in {native_language} — what exactly is wrong, or why it was accepted"}}
JSON only, no markdown.
"""

WORD_ORDER_CHECK_PROMPT = """
A build-the-Polish-sentence-from-words task. The user arranged the words in a different order than the reference.
The words in both variants are IDENTICAL — only the order differs.

Reference: "{correct_answer}"
User's answer: "{user_answer}"
Sentence meaning: "{translation}"

CHECK ALGORITHM (follow step by step, do not skip):
1. Find every preposition (z, ze, w, we, do, na, po, od, dla, przy, o, u, przed, za, nad, pod, bez, przez).
   Its noun/pronoun must come IMMEDIATELY AFTER the preposition. If a preposition is detached — correct: false.
2. The particle "nie" must stand directly before the verb it negates. Otherwise — false.
3. A question word (co, kto, gdzie, kiedy, dlaczego, jak, czy) must be at the beginning. Otherwise — false.
4. A vocative/address phrase (Panie Kowalski, mamo, Aniu) may stand at the BEGINNING or at the END
   of the sentence — both are correct. Ignore commas and capitalisation entirely.
5. If steps 1-4 pass and the order sounds natural to a native speaker — correct: true.

EXAMPLES:
reference "Wychodzę z domu po pracy.":
✓ "Po pracy wychodzę z domu" → true (fronted adverbial — natural)
✗ "Wychodzę domu z po pracy" → false (prepositions z and po detached from their nouns)
✗ "Z po pracy domu wychodzę" → false (meaningless jumble)
reference "Nie mam czasu.":
✓ "Czasu nie mam" → true (emphatic order — acceptable)
✗ "Mam nie czasu" → false (nie not before the verb)
reference "Panie Kowalski, proszę o dokumenty.":
✓ "Proszę o dokumenty Panie Kowalski" → true (address moved to the end — natural)
✗ "Proszę Panie o dokumenty Kowalski" → false (address phrase torn apart)

Answer with JSON: {{"correct": true/false}}
JSON only, no markdown.
"""

CHAT_ROLEPLAY_PROMPT = """
You are running a ROLE-PLAY DIALOGUE for Polish practice.
Your role: {role}. Situation: "{title}".
User level: {level}. User's native language: {native_language}.

Rules:
- Stay IN CHARACTER. Speak ONLY Polish, naturally and true to the situation.
- Short, lively lines; vocabulary difficulty matched to level {level}.
- Drive the dialogue forward: react, ask counter-questions, develop the scenario toward a natural ending.
- Do NOT correct grammar along the way — a debrief happens separately at the end. If something is truly unintelligible, ask again while staying in character.
- No explanations in {native_language} and no breaking character.
"""

DIALOGUE_DEBRIEF_PROMPT = """
You are a friendly Polish teacher. The student has just finished a role-play dialogue: "{title}".
Here are their lines (in Polish):
{user_messages}

Give a short debrief in {native_language}, markdown format:
1. **What went well** — 1-2 points, sincere.
2. **What to work on** — 2-3 GENTLE corrections in the format: "*[what they wrote]* → *[correct version]* — short explanation".

Flag only real mistakes. If there are almost none — praise them and give 1 tip for enriching their speech.
Be brief, warm and encouraging. The entire debrief must be in {native_language}.
"""

CHAT_SYSTEM_PROMPT = """
You are a friendly Polish conversation partner.
User level: {level}. User's native language: {native_language}.
User's weak spots: {weak_spots}.

Rules:
- Reply in Polish
- Adapt vocabulary difficulty to the level
- If you see a grammar mistake — at the end of your message add one line in {native_language}:
  "By the way: [what they wrote] → [correct version] — [one-word explanation]" (phrase it naturally in {native_language})
- Correct no more than 1 mistake at a time
- First respond to the topic, then the correction
- Be brief and natural
"""

WRITING_EVALUATION_PROMPT = """
You are a Polish language examiner, level B1.
Task: {task_description}
Student's answer: {student_text}

Grade each criterion (0-5 points):
1. Task completion
2. Vocabulary
3. Grammar
4. Text coherence

Answer with JSON:
{{
  "scores": {{"task": 0, "vocabulary": 0, "grammar": 0, "coherence": 0}},
  "total": 0,
  "feedback": "2-3 sentences of overall commentary in {native_language}",
  "corrections": ["concrete mistake 1", "concrete mistake 2"]
}}
JSON only, no markdown. feedback and corrections in {native_language}.
"""

PLACEMENT_TEST_PROMPT = """
You generate a Polish placement test.
Test taker's native language: {native_language}.

Generate exactly 10 questions to determine the level (A0-A2):
- Questions 1-2: word translation (level A0) — what is the word in Polish
- Questions 3-4: pick the correct form (level A1) — cases
- Questions 5-6: verb ending (level A1) — conjugation
- Questions 7-8: understand a phrase (level A2) — what the phrase means
- Questions 9-10: build a phrase (level A2) — word order

question text is written in {native_language}.

Answer ONLY with a valid JSON array, no markdown:
[
  {{
    "id": 1,
    "type": "multiple_choice",
    "question": "question text in {native_language}",
    "options": ["option1", "option2", "option3", "option4"],
    "correct_answer": "the correct option",
    "level": "A0"
  }},
  ...
]
"""

# Shared rules block — no format variables, concatenated into the generator prompts.
_EXERCISE_COMMON_RULES = (
    "GENERAL RULES (mandatory for all types):\n"
    '- Grammar: every form correct. Especially: po+miejscownik (po pracy, po spotkaniu), '
    'od/proszę+dopełniacz (od bólu, proszę soku), kilka/dużo+dopełniacz pl. (kilka rolek — not rolki)\n'
    '- Living examples: not "Ala ma kota", not a 1970s textbook — real conversational situations\n'
    '- VARIETY OF CONSTRUCTIONS: do not open exercises the same way. Avoid worn-out templates '
    '("Na stole leży...", "Nie mam czasu na...", "To jest prezent dla..."). Every exercise — a new opening, '
    'a different subject, verb, situation\n'
    '- Difficulty strictly matches the user level\n'
    '- The "explanation" field is ALWAYS in the user\'s native language\n'
    '- Forbidden: vulgar, rude, anatomical expressions\n'
    '- Only real, existing Polish words and idioms — never invent any\n'
    '- No more than 2 exercises on one theme\n'
    '- If the answer is a numeral written as a word (dwa, piątego): in fill_blank/letter_tiles the question '
    'MUST contain the digit as a cue in parentheses, e.g. "Mam ___ lata. (2)" — otherwise any number fits; '
    'NEVER split a compound numeral with the blank — ___ must cover the whole number. '
    'In order_words NO digit cue — the numeral word is already visible among the pieces\n'
    '- Add "(mówi kobieta)"/"(mówi mężczyzna)" markers only when the speaker\'s gender REALLY affects the answer '
    '(e.g. poszłam vs poszedłem); if the answer is the same for both genders — no marker\n'
    '- In multiple_choice all options are in the same language as the question: '
    'question in the user\'s native language → options in that language; question in Polish → options in Polish\n'
    "- LANGUAGE OF FIELDS: translation, explanation, hint and all word_hints VALUES are written in the "
    "user's native language — never in English (unless English IS their native language) and never in any third language"
)

# Grammar batch prompt: fill_blank, multiple_choice
GRAMMAR_EXERCISES_PROMPT = (
    "You generate Polish language exercises.\n"
    "Level: {level}. User's native language: {native_language}.\n"
    "Themes to draw examples from (use them, not abstract phrases): {interest_themes}\n\n"
    + _EXERCISE_COMMON_RULES + "\n\n"
    "Generate {count} exercises. Types: fill_blank, multiple_choice. Mix evenly.\n\n"
    "FILL_BLANK — insert the missing word:\n"
    "- EXACTLY ONE ___ in question; the sentence is complete and unambiguous\n"
    "- The answer is NOT present in question in any form (not in parentheses, not before/after ___)\n"
    "- FORBIDDEN to add parenthesised hints for words that are NOT part of correct_answer: "
    "if the answer is only «firmie», you must not write «(w)» in the question — it confuses the user into typing «w firmie»\n"
    "- FORBIDDEN: masculine inanimate in biernik (telefon, dom, film — form unchanged → trivial answer); "
    "use animate (kota, chłopca) or feminine (herbatę, kobietę)\n"
    "- FORBIDDEN: spelling-out tasks (przeliteruj/przeliterować) — the letter_tiles type exists for that\n"
    "- correct_answer: one word or a fixed phrase, no slash /\n"
    "- hint: only the grammatical category (e.g. \"biernik l.poj.\"), NEVER the answer itself\n"
    "  SELF-CHECK hint/explanation: look at correct_answer — what ending does it have? Which case does that ending mark?\n"
    "  Make sure the case you name matches the actual form of the answer. Frequent mix-ups:\n"
    "  kilka/ile/wiele/parę + noun → ALWAYS dopełniacz l.mn. (not narzędnik)\n"
    "  proszę czegoś → dopełniacz (not narzędnik)\n"
    "  after numerals 2/3/4 → dopełniacz l.poj.; after 5+ → dopełniacz l.mn.\n"
    "  IF correct_answer is a preposition (po, na, w, do, z, przy, nad etc.):\n"
    "  make sure the noun RIGHT AFTER ___ is already in the correct case:\n"
    "  po + miejscownik (po spotkaniu, not po spotkania)\n"
    "  na/w + miejscownik (na stole, w domu) or biernik (na stół, w las)\n"
    "  do/z/od/bez + dopełniacz (do sklepu, z domu)\n"
    "- If speaker gender matters — append \"(mówi kobieta)\" to the question\n"
    "- word_hints: Polish words of the question → {native_language}\n\n"
    "MULTIPLE_CHOICE — 4 options:\n"
    "- correct_answer matches one of options VERBATIM — double-check\n"
    "- All 4 options are substantially different (different cases/forms, not one word with commentary)\n"
    "- THE ANSWER MUST FOLLOW UNAMBIGUOUSLY FROM THE POLISH SENTENCE ITSELF, not from the translation.\n"
    "  VIOLATION: «Spotkanie odbędzie się dwudziestego drugiego ___ (miesiąc)» with month options —\n"
    "  the sentence gives NO cue for a specific month, any fits grammatically → unsolvable.\n"
    "  If the options are a lexical choice (months, cities, names), the sentence MUST contain context\n"
    "  that determines the single correct one. If the choice is grammatical (case/form) — always fine.\n"
    "- If the question is about meaning — all options in {native_language}\n"
    "- FORBIDDEN: meta-questions like 'What happens to X in the context of Y?' where the correct form is already visible\n"
    "  Right: a Polish sentence with ___ (Zaprosiłem do domu ___ kolegę.) → form options\n"
    "  Wrong: 'What happens to kolega in the context Zaprosiłem do domu ___ kolegę?' — the answer is visible\n"
    "- word_hints: Polish words of the question → {native_language} (1-3 key ones, excluding the answer options)\n\n"
    "Answer ONLY with a valid JSON array, no markdown. Example values for translation/explanation/hint/word_hints "
    "are shown in English below — you MUST write them in {native_language}:\n"
    "[\n"
    '  {{"type": "fill_blank", "question": "Poproszę ___ kawy.", "correct_answer": "filiżankę", "options": null, "hint": "biernik od filiżanka", "explanation": "After poproszę — biernik", "translation": "A cup of coffee, please.", "word_hints": {{"poproszę": "please give me", "kawy": "coffee"}}}},\n'
    '  {{"type": "multiple_choice", "question": "Lubię ___ (herbata).", "options": ["herbatę", "herbaty", "herbacie", "herbata"], "correct_answer": "herbatę", "hint": null, "explanation": "After lubię — biernik: herbata→herbatę", "translation": null, "word_hints": {{"lubię": "I like"}}}}\n'
    "]"
)

# judge_sentence prompt — separate, to enforce the 50/50 true/false split
JUDGE_EXERCISES_PROMPT = (
    "You generate judge_sentence exercises for Polish.\n"
    "Level: {level}. User's native language: {native_language}.\n"
    "Themes for examples: {interest_themes}\n\n"
    + _EXERCISE_COMMON_RULES + "\n\n"
    "Generate exactly {count} judge_sentence exercises.\n"
    "STRICT: exactly half with correct_answer=\"true\", exactly half with correct_answer=\"false\".\n"
    "If {count} is odd — one extra true is allowed.\n\n"
    "Format of each exercise:\n"
    "- question: a Polish sentence (sometimes with a deliberate error)\n"
    '- correct_answer: strictly "true" or "false"\n'
    "- explanation: in {native_language} — why it is correct, or what exactly is wrong\n"
    "- translation: full translation of the sentence into {native_language} (mandatory!)\n"
    "- word_hints: key Polish words → {native_language}\n\n"
    "FOR FALSE ITEMS — algorithm:\n"
    "1. Pick a concrete error type from the list below\n"
    "2. Build a sentence with that error baked in (suspicious, not blatant)\n"
    "3. SELF-CHECK: can you name the SPECIFIC wrong word/form and how to fix it?\n"
    "   If not — the sentence is correct; make it TRUE.\n\n"
    "Error types for false (vary them, don't repeat one type):\n"
    "- Wrong case after a preposition: \"Idę do sklep\" (→ sklepu), \"Mieszkam na ulica\" (→ ulicy)\n"
    "- Wrong noun-adjective gender agreement: \"dobry kobieta\" (→ dobra), \"nowy książka\" (→ nowa)\n"
    "- 3rd person with ja: \"ja poszedł\"/\"ja poszła\" (→ poszedłem/poszłam), \"ja był\" (→ byłem)\n"
    "- 2nd person with ja: \"ja jesteś\" (→ jestem), \"ja masz\" (→ mam)\n"
    "- Wrong verb aspect/tense: \"Wczoraj czytam książkę\" (past → czytałem)\n"
    "- Wrong government: \"Lubię z muzyką\" (→ lubię muzykę), \"Słucham muzyka\" (→ muzyki)\n"
    "- Wrong numeral form: \"Mam dwa siostry\" (→ dwie), \"pięć chłopcy\" (→ chłopców)\n\n"
    "ABSOLUTE BANS for false (these constructions are ALWAYS correct — never use them as errors):\n"
    "- «ja jestem zmęczony» / «ja jestem zmęczona» — both correct (depends on speaker's gender)\n"
    "- «ja jestem [any adjective]» — agreement with the speaker, not an error\n"
    "- «zapomniał swojego [noun]» — zapomnieć governs the genitive, swojego = correct\n"
    "- «swojego», «swojej», «swojemu» — case forms of swój: CORRECT\n"
    "- Any correct Polish sentence you are «not sure» about — make it TRUE, do not invent errors\n\n"
    "FOR TRUE ITEMS:\n"
    "- Include forms that look «suspicious» but are actually correct\n"
    "- Examples: poszedłem/poszłam, byłem/byłam, widziałem ją, proszę kawy, kilka dni\n"
    "- «ja byłem»/«ja byłam», «ja poszedłem»/«ja poszłam» — CORRECT (pronoun redundant but not an error)\n"
    "- «ja był»/«ja poszedł» — WRONG (that is 3rd person, not 1st). Do not confuse the two cases.\n"
    "- «Mój kolega zapomniał swojego biletu» — CORRECT (genitive after zapomnieć + swojego correct)\n"
    "- «Ona jest zadowolona» — CORRECT (feminine adjective with ona)\n\n"
    "FINAL CHECK before every false: the explanation MUST name the specific wrong word and its\n"
    "correct form. If you cannot — change the item to true.\n\n"
    "Answer ONLY with a valid JSON array, no markdown. Example values for explanation/translation/word_hints "
    "are shown in English — you MUST write them in {native_language}:\n"
    "[\n"
    '  {{"type": "judge_sentence", "question": "Wczoraj ja poszedłem do kina.", "correct_answer": "true", "options": null, "hint": null, "explanation": "poszedłem — correct 1st person sg. masculine past form", "translation": "Yesterday I went to the cinema.", "word_hints": {{"wczoraj": "yesterday", "kina": "cinema (gen.)"}}}},\n'
    '  {{"type": "judge_sentence", "question": "Ona jest dobry lekarz.", "correct_answer": "false", "options": null, "hint": null, "explanation": "ona is feminine — it must be dobra lekarka (or dobry lekarz with on)", "translation": "She is a good doctor.", "word_hints": {{"lekarz": "doctor"}}}}\n'
    "]"
)

# Post-validation: re-check judge_sentence items marked "false" — Mistral routinely
# invents a non-existent error and writes a self-contradicting explanation. A second
# strict pass confirms the claimed error is real; unconfirmed items are dropped.
JUDGE_VERIFY_PROMPT = (
    "You are a strict Polish proofreader. You are given sentences flagged as CONTAINING AN ERROR.\n"
    "For EACH one, decide whether it contains a REAL grammatical error.\n\n"
    "Verification rules:\n"
    "- The sentence is grammatically CORRECT for a native speaker → verdict \"correct\" (the flag was wrong).\n"
    "- There is a real error AND it matches the claimed one → verdict \"error\".\n"
    "- You are unsure, cannot name the error, or the claim is incoherent/contradictory → \"correct\".\n"
    "REMEMBER (always correct, NOT errors): «ja jestem zmęczony/zmęczona», «byliśmy zmęczonymi sportowcami» "
    "(instrumental after być — correct), «zapomniał swojego/jego biletu», free word order, "
    "«specjalnym autobusem» (instrumental), «o trzy kilometry dłuższa» (correct government).\n\n"
    "You get a JSON array of objects {{id, sentence, claimed_error}}.\n"
    "Answer ONLY with a valid JSON array of the same size: "
    '[{{"id": <id>, "verdict": "error"|"correct"}}], no markdown.\n\n'
    "Sentences:\n{items}"
)

# Lexical batch prompt: translate, order_words
LEXICAL_EXERCISES_PROMPT = (
    "You generate Polish language exercises.\n"
    "Level: {level}. User's native language: {native_language}.\n"
    "Themes to draw examples from (use them, not abstract phrases): {interest_themes}\n\n"
    + _EXERCISE_COMMON_RULES + "\n\n"
    "Generate {count} exercises. Types: translate, order_words. Mix evenly.\n"
    "(Do NOT generate idioms here — they have a dedicated prompt.)\n\n"
    "TRANSLATE — phrase translation:\n"
    "- question: a short phrase in {native_language}, ≤8 words\n"
    "- correct_answer: the Polish translation\n"
    "- If gender matters — state it in the question, e.g. \"I went (a woman speaking)\" phrased in {native_language}\n"
    '- Only living, natural phrases in {native_language} — NO calques from other languages ("it costs an arm and a leg" translated literally — forbidden)\n'
    '- FORBIDDEN meta-tasks ("translate idiom X word by word") — only real phrases\n'
    "- word_hints: words of the {native_language} phrase → their Polish equivalents\n\n"
    "ORDER_WORDS — arrange the words:\n"
    '- question: the words of correct_answer joined with " / " — EXACTLY the same words in the same forms\n'
    "- NO extra words — the system checks the exact multiset\n"
    "- If several orders are correct — list ALL variants in correct_answer separated by ' / '\n"
    "  Example: a time adverb (wczoraj, jutro, dziś, zawsze, często) can go first or last;\n"
    "  then correct_answer = \"Wczoraj czytałem tę książkę. / Czytałem tę książkę wczoraj.\"\n"
    "- hint: the grammar rule, without naming words from the answer; do NOT claim a single order when several are valid\n"
    "- word_hints: Polish words → {native_language}\n\n"
    "Answer ONLY with a valid JSON array, no markdown. Example question/hint/word_hints values are shown "
    "in English — you MUST write them in {native_language}:\n"
    "[\n"
    '  {{"type": "translate", "question": "I am already going home.", "correct_answer": "Już idę do domu.", "options": null, "hint": null, "explanation": "już = already, idę = I am going", "translation": null, "word_hints": {{"already": "już", "going": "idę", "home": "do domu"}}}},\n'
    '  {{"type": "order_words", "question": "tę / wczoraj / czytałem / książkę", "correct_answer": "Wczoraj czytałem tę książkę. / Czytałem tę książkę wczoraj.", "options": null, "hint": "Polish word order is flexible — a time adverb can open or close the sentence", "explanation": null, "translation": null, "word_hints": {{"wczoraj": "yesterday", "czytałem": "I read (past)", "tę": "this", "książkę": "book"}}}}\n'
    "]"
)

WORD_DEFINITION_PROMPT = (
    "You generate Polish language exercises.\n"
    "Level: {level}. User's native language: {native_language}.\n\n"
    + _EXERCISE_COMMON_RULES + "\n\n"
    "Generate {count} word_definition exercises — riddle descriptions.\n"
    "The user reads a description of a word in Polish and types the answer (a Polish word).\n\n"
    "RULES:\n"
    "- type: always \"word_definition\"\n"
    "- question: a description of the word in Polish, 1-2 sentences. Natural, living Polish.\n"
    "  FORBIDDEN: using the word itself, same-root or derived words in the description.\n"
    "  VIOLATION: answer=apteka, question contains 'aptekarz' — the root 'aptek' gives the answer away.\n"
    "  VIOLATION: answer=pływać, question contains 'pływak' or 'pływalnia'.\n"
    "  Think of the game Alias — describe through meaning, function, category, with no related words.\n"
    "  FORBIDDEN: putting ___ in question — this is not fill_blank\n"
    "  FACTUAL ACCURACY: every claim in the description must be TRUE of the answer and point\n"
    "  to it UNAMBIGUOUSLY. VIOLATION: answer=cytryna (lemon), description «owoc czerwony lub\n"
    "  zielony» — a lemon is yellow; the description is false and fits other fruits. Check every attribute:\n"
    "  colour, taste, size, where it occurs — everything must match this exact word.\n"
    "  The description must rule out similar words (not «a sour fruit» — that fits lemon, lime and grapefruit).\n"
    "- correct_answer: ONE Polish word in dictionary form (noun in nom., verb in infinitive).\n"
    "  STRICTLY one word — no spaces, no underscores. Reflexive verbs do NOT qualify (mycie się) — pick a non-reflexive word.\n"
    "- hint: first letter + word category, NOT the word itself (e.g. \"K... — napój\")\n"
    "  The hint is in Polish too\n"
    "- translation: translation of correct_answer into {native_language} — shown after the answer\n"
    "- explanation: why the description fits, in {native_language} (optional)\n"
    "- options: null\n"
    "- word_hints: TRANSLATE ALL meaningful Polish words of the description → {native_language} "
    "(nouns, verbs, adjectives — all but pure function words). The user must be able to "
    "understand the riddle, so there should be many hints (usually 5-10), not 1-2\n\n"
    "{candidate_words}"
    "Pick concrete words that are easy to describe — objects, animals, food, actions.\n"
    "Avoid abstract concepts (miłość, wolność) — they are hard to describe unambiguously.\n"
    "PREFER dense words that name a whole concept in one word (one Polish word = "
    "something that takes several words to say in the user's language): such words are more interesting than trivial kot/kawa. "
    "Pick DIFFERENT words every time — do not repeat the same riddles from session to session.\n"
    "The description's difficulty must match the user's level {level}.\n\n"
    "Answer ONLY with a valid JSON array, no markdown. Example explanation/translation/word_hints values are "
    "shown in English — you MUST write them in {native_language}:\n"
    "[\n"
    '  {{"type": "word_definition", "question": "To jest napój, który pijemy rano. Może być czarna lub z mlekiem i cukrem.", "correct_answer": "kawa", "options": null, "hint": "K... — napój", "explanation": "Coffee — one of the most popular drinks in Poland", "translation": "coffee", "word_hints": {{"napój": "drink", "rano": "in the morning", "mlekiem": "milk (instr.)", "cukrem": "sugar (instr.)"}}}},\n'
    '  {{"type": "word_definition", "question": "To zwierzę domowe, które miauczy i lubi spać na kanapie.", "correct_answer": "kot", "options": null, "hint": "K... — zwierzę domowe", "explanation": null, "translation": "cat", "word_hints": {{"zwierzę": "animal", "miauczy": "meows", "kanapie": "couch (loc.)"}}}}\n'
    "]"
)

LETTER_TILES_PROMPT = (
    "You generate Polish language exercises.\n"
    "Level: {level}. User's native language: {native_language}.\n"
    "Themes for examples: {interest_themes}\n\n"
    + _EXERCISE_COMMON_RULES + "\n\n"
    "Generate {count} letter_tiles exercises.\n"
    "The user assembles a word from shuffled letter tiles. Two valid formats — mix both:\n\n"
    "FORMAT A — a full sentence (the app itself picks which word to blank out):\n"
    "- question: a COMPLETE natural Polish sentence of 6-12 words, NO ___ and NO letter lists.\n"
    "  Include at least one interesting word of 5+ letters (ideally with diacritics ą ę ó ś ć ź ż ń ł)\n"
    "- correct_answer: null — the app removes a word itself, so the sentence, translation and\n"
    "  hints always stay consistent\n"
    "- hint: null\n"
    "- translation: the full sentence in {native_language}\n"
    "- word_hints: MANDATORY — every meaningful Polish word of the sentence → {native_language}.\n"
    "  A format-A item without word_hints will be DISCARDED by the validator — the user cannot understand the sentence.\n\n"
    "FORMAT B — pure spelling:\n"
    "- question: an instruction meaning 'Write in Polish: [word in {native_language}]' — the instruction itself is written in {native_language}, WITHOUT ___\n"
    "- correct_answer: the Polish word STRICTLY in dictionary form (nominative sg. / infinitive).\n"
    "  There is NO sentence context in format B, so a case-inflected form (marchewką) is meaningless — always the base form (marchewka)\n"
    "- Use for words with non-trivial spelling: szczęście, marchewka, grzeczny, czekolada\n"
    "- hint: first letter + short category (e.g. 'sz... — something sweet', phrased in {native_language})\n"
    "- translation: null\n"
    "- word_hints: null\n\n"
    "GENERAL RULES:\n"
    "- correct_answer: ONE word, no spaces\n"
    "- FORBIDDEN: listing the letters inside the question ('ułóż z liter: a, w, k...') — the app already\n"
    "  shows the letter tiles; an enumeration only leaks the answer\n"
    "- FORBIDDEN: masculine inanimate biernik (telefon, dom — form unchanged → trivial)\n"
    "- Prefer words with diacritics: ą ę ó ś ć ź ż ń ł\n"
    "- explanation: in {native_language} — why this form or spelling\n\n"
    "Answer ONLY with a valid JSON array, no markdown. Example translation/explanation/word_hints/question-instruction "
    "values are shown in English — you MUST write them in {native_language}:\n"
    "[\n"
    '  {{"type": "letter_tiles", "question": "Lubię pić gorącą kawę rano.", "correct_answer": null, "options": null, "hint": null, "explanation": "After lubię pić — biernik", "translation": "I like drinking hot coffee in the morning.", "word_hints": {{"lubię": "I like", "pić": "to drink", "gorącą": "hot", "kawę": "coffee", "rano": "in the morning"}}}},\n'
    '  {{"type": "letter_tiles", "question": "Write in Polish: happiness", "correct_answer": "szczęście", "options": null, "hint": "sz... — a feeling", "explanation": "szczęście — one of the hardest words to spell: sz+cz+ę", "translation": null, "word_hints": null}}\n'
    "]"
)

TOPIC_EXAMPLE_PROMPT = """
You are a Polish teacher. User level: {level}. User's native language: {native_language}.
Topic: {topic_title}.

Give one more living example on this topic — a sentence or a dialogue with a translation into {native_language}.
The example must be new, not a repeat of previous ones.
Format: markdown, brief.
"""

TOPIC_EXERCISES_PROMPT = """
You generate Polish language exercises.
Topic: {topic_title}. Level: {level}. Language of explanations: {native_language}.

Generate exactly {count} exercises ONLY on this topic.
Use ONLY the types "multiple_choice" and "fill_blank", roughly half each.

Rules:
- multiple_choice: always exactly 4 options in "options"; "correct_answer" equals one option verbatim. If the question is about the meaning of a word/phrase — options and correct_answer in {native_language}. The "explanation" field is ALWAYS in {native_language}.
- fill_blank: "question" MUST contain ___ at the gap. The answer word must NOT appear in the question text in any form (not in parentheses, not nearby). Hints go only into the "hint" field.
- VARIETY IS MANDATORY: each exercise must test a different construction, word or rule — never repeat the same word/form twice within one set. If the topic spans several constructions (e.g. different question words or different cases), spread the exercises so each construction appears at least once.

Answer ONLY with a valid JSON array, no markdown:
[
  {{
    "type": "multiple_choice",
    "question": "a question in {native_language} or a Polish sentence",
    "options": ["option1", "option2", "option3", "option4"],
    "correct_answer": "option1",
    "explanation": "short explanation in {native_language}"
  }},
  {{
    "type": "fill_blank",
    "question": "Wczoraj ja ___ (iść) do sklepu.",
    "correct_answer": "szłam",
    "hint": "hint in {native_language}",
    "explanation": "explanation in {native_language}"
  }}
]
"""

READING_TEXT_PROMPT = """
Generate a Polish text for a reading exercise (level B1).
Length: 200-300 words. Topic: {topic}.
Style: modern, lively, interesting.

After the text, generate 5 multiple-choice questions (4 options each).

Answer ONLY with valid JSON, no markdown:
{{
  "text": "the Polish text",
  "questions": [
    {{
      "question": "the question",
      "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
      "correct": "A) option1",
      "explanation": "explanation in {native_language}"
    }}
  ]
}}
"""

READING_PROMPT = (
    "You are building a READING COMPREHENSION exercise for Polish.\n"
    "Reader level: {level}. Reader's native language: {native_language}.\n"
    "Themes to choose from (pick one, a lively one): {interest_themes}\n\n"
    "Generate ONE coherent Polish text and comprehension questions.\n\n"
    "TEXT:\n"
    "- 4-7 sentences, natural living Polish, STRICTLY at level {level} (no harder)\n"
    "- genre: a short story, a note, a letter or a dialogue — something meaningful\n"
    "- NOT a list of facts but a coherent text\n\n"
    "QUESTIONS (exactly 3):\n"
    "- about the content, in Polish; the answer follows UNAMBIGUOUSLY from the text\n"
    "- each: 4 options, exactly one correct\n"
    "- options — the FULL answer text WITHOUT letter labels (NOT 'A.', 'B)')\n"
    "- correct_answer — VERBATIM the full text of the correct option (NOT the letter 'B')\n"
    "- vary: a fact, a detail, meaning/inference\n\n"
    "Also return:\n"
    "- translation: translation of the WHOLE text into {native_language}\n"
    "- word_hints: 5-8 key Polish words of the text → {native_language}\n\n"
    "Answer ONLY with a valid JSON object, no markdown. The explanation values are shown in English — "
    "write them in {native_language}:\n"
    "{{\n"
    '  "type": "reading",\n'
    '  "title": "a short title in Polish",\n'
    '  "text": "A Polish text of 4-7 sentences.",\n'
    '  "translation": "The full translation of the text.",\n'
    '  "word_hints": {{"slowo": "translation"}},\n'
    '  "questions": [\n'
    '    {{"question": "Gdzie mieszka babcia?", "options": ["W dużym mieście", "W małym domu na wsi", "Nad morzem", "W górach"], "correct_answer": "W małym domu na wsi", "explanation": "The text says the grandmother lives in the countryside."}}\n'
    "  ]\n"
    "}}"
)

# On-demand dictionary for any clicked word in an exercise sentence (feedback: only some
# words had hints; the user wants EVERY word translatable). Cached in word_translation_cache.
WORD_TRANSLATE_PROMPT = (
    "Translate one Polish word for a learner.\n"
    'Word: "{word}"\n'
    'Sentence it appeared in (context): "{context}"\n\n'
    "Give the translation into {native_language} of THIS word as used in THIS context.\n"
    "If the word is an inflected form, also give its Polish dictionary form (lemma).\n"
    'Answer ONLY with valid JSON, no markdown: '
    '{{"translation": "<translation in {native_language}>", "lemma": "<Polish dictionary form>"}}'
)

WORD_DEFINITION_VERIFY_PROMPT = (
    "You are a strict editor of word-riddles for Polish learners.\n"
    "You get a list of: a word description (in Polish) and the intended answer.\n"
    "For EACH one decide whether the riddle is sound:\n"
    "- verdict \"ok\" — ALL attributes in the description are factually TRUE of the answer AND the description "
    "points unambiguously to it (does not fit another common word).\n"
    "- verdict \"bad\" — there is a factual error (e.g. 'jabłko ... bardzo kwaśny' — an apple is usually "
    "sweet, not sour) OR the description is ambiguous (fits marchew, pietruszka and dynia alike).\n"
    "When in doubt — \"bad\".\n\n"
    "You get a JSON array of {{id, description, answer}}.\n"
    "Answer ONLY with a valid JSON array of the same size: "
    '[{{"id": <id>, "verdict": "ok"|"bad"}}], no markdown.\n\n'
    "Riddles:\n{items}"
)

VOCAB_GENERATION_PROMPT = """
You generate vocabulary for Polish learners.
Current user level: {level}. User's native language: {native_language}.

Generate {count} Polish words/expressions. The goal is to EXPAND vocabulary and PULL the user UP:
give words of level {level} AND 1-2 steps above (up to B2 max, NOT higher).
In the "level" field state the REAL level of each word (e.g. A2, B1, B2).

VARIETY IS MANDATORY — not just basic nouns about food/home:
- different parts of speech: verbs, adjectives, ADVERBS, conjunctions and connectors (jednak, mimo to, dlatego, chociaż), prepositions
- living collocations and fixed expressions (zwracać uwagę, mieć ochotę, dać radę)
- less trivial, "interesting" words rather than the school minimum
Rotate domains: emotions and character, work and study, culture, technology, nature, relationships, abstract concepts, daily life.

STRICTLY do not repeat (already in the dictionary): {avoid_words}

Answer ONLY with a valid JSON array, no markdown:
[
  {{"polish": "...", "translation_ru": "...", "translation_en": "...", "example_sentence": "...", "level": "B1"}}
]

Requirements:
- Real words (not invented), verify the spelling; example_sentence 5-10 Polish words
- "polish": ONE word in dictionary form (noun — nom. sg., verb — infinitive, adj. — masc.) OR one fixed phrase. No variants with /
- "translation_ru": precise RUSSIAN translation; several equal variants — separated by ' / '; do not mix different senses of a polysemous word
- "translation_en": precise ENGLISH translation, same rules. BOTH translation fields are always required regardless of the user's native language (the dictionary is shared between users)
"""

GRAMMAR_EXAM_PROMPT = """
Generate 20 Polish grammar questions at level B1.
Cover all areas: cases, verb aspects, tenses, the conditional.
The "explanation" field is written in {native_language}.

Answer ONLY with a valid JSON array, no markdown:
[
  {{
    "question": "Mam ___ (brat)",
    "options": ["brat", "brata", "bracie", "bratem"],
    "correct_answer": "brata",
    "explanation": "After mam — biernik of an animate masculine noun: brat → brata"
  }}
]
"""

# Dedicated prompt for idiom flashcards. Topic-FREE: Mistral draws REAL idioms from its
# own knowledge and is never forced to invent an idiom to fit a grammar topic (that
# produced fabricated garbage).
IDIOM_FLASHCARD_PROMPT = (
    "You are an expert in Polish phraseology.\n"
    "User level: {level}. User's native language: {native_language}.\n\n"
    "Generate {count} flashcards with REAL Polish idioms and fixed expressions.\n\n"
    "HARD RULES:\n"
    "- ONLY idioms/phrasemes/sayings that really exist and are used in living Polish speech.\n"
    "  If you are not 100% sure the phrase exists — do NOT include it. Fewer but real.\n"
    "- Do NOT invent plausible-sounding phrases. Examples of invented garbage (do NOT do this): "
    "'pazur w kieszeni', 'zielony kot na dachu'.\n"
    "- Every idiom MUST contain a verb (mieć, robić, wziąć, być, lać, rzucać, trzymać etc.).\n"
    "  FORBIDDEN: single words, adjective+noun without a verb (zielone drzewo), plain word combinations.\n"
    "- Variety: different idioms every time, different verbs and domains (emotions, work, relationships, money, time).\n"
    "- Difficulty matched to level {level}: for A0-A1 — the most frequent everyday idioms; higher — rarer ones allowed.\n\n"
    "FIELDS of each card:\n"
    "- type: always \"flashcard\"\n"
    "- question: the Polish idiom itself, whole (no ___, no gaps)\n"
    "- correct_answer: the MEANING translated into {native_language} (what it means), NOT literal\n"
    "- translation: the literal translation into {native_language} (marked as literal) — so the wordplay is visible\n"
    "- explanation: short note in {native_language} — when and how it is used (1 sentence)\n"
    "- options: null, hint: null, word_hints: null\n\n"
    "Answer ONLY with a valid JSON array, no markdown. Example correct_answer/translation/explanation values are "
    "shown in English — you MUST write them in {native_language}:\n"
    "[\n"
    '  {{"type": "flashcard", "question": "mieć muchy w nosie", "correct_answer": "to be in a bad mood, to sulk", "options": null, "hint": null, "explanation": "About a person who is irritated for no clear reason", "translation": "lit. \'to have flies in one\'s nose\'", "word_hints": null}},\n'
    '  {{"type": "flashcard", "question": "rzucać słowa na wiatr", "correct_answer": "to make empty promises, not keep one\'s word", "options": null, "hint": null, "explanation": "About someone who promises but does not deliver", "translation": "lit. \'to throw words to the wind\'", "word_hints": null}}\n'
    "]"
)

IDIOM_DRILL_PROMPT = """
The user is learning Polish (level {level}, native language: {native_language}).
They already know the meaning of these expressions (seen as flashcards):
{expressions}

For each expression create ONE exercise that forces the user to
REPRODUCE the key word — not merely recognize the expression.

TYPE SELECTION RULES:
- "fill_blank" — remove ONE key word of the expression, replace with ___.
  The rest of the expression + a context sentence stay in the question.
- "letter_tiles" — same, but correct_answer is strictly one word with no spaces.
  Prefer letter_tiles for words with Polish diacritics (ą ę ó ś ć ź ż ń ł).

STRICT RULES:
- correct_answer = the one word the user must type/assemble.
  For fill_blank — may be a short phrase (e.g. «na plecach»), but one word is better.
  For letter_tiles — ONLY one word, NO spaces.
- The answer must NOT appear in the question even partially.
- hint: a short description of the expression in {native_language} that does NOT reveal the answer.
- explanation: what the expression means, how it is used — in {native_language}.
- question: a living sentence with the gap, not just the expression with ___.
- translation: MANDATORY — the full sentence translated into {native_language} with the word itself in place of ___.
- word_hints: MANDATORY — every meaningful Polish word of the sentence (except the answer) → {native_language}.
  Without word_hints the item will be DISCARDED — the user cannot understand the sentence.

Answer ONLY with a valid JSON array (one object per expression). Example hint/explanation/translation/word_hints
values are shown in English — you MUST write them in {native_language}:
[
  {{"type": "fill_blank", "question": "On zawsze ma ___ w nosie — nigdy nie jest w dobrym humorze.", "correct_answer": "muchy", "options": null, "hint": "the idiom for being in a bad mood", "explanation": "«mieć muchy w nosie» — to be irritated, out of sorts", "translation": "He always has flies in his nose — he is never in a good mood.", "word_hints": {{"zawsze": "always", "nosie": "nose (loc.)", "nigdy": "never", "dobrym": "good (loc.)", "humorze": "mood (loc.)"}}}},
  {{"type": "letter_tiles", "question": "Nie masz ___ na plecach — nie możesz wszystkiego kontrolować.", "correct_answer": "oczu", "options": null, "hint": "the saying about not seeing everything", "explanation": "«nie mieć oczu na plecach» — you cannot keep track of everything at once", "translation": "You don't have eyes in the back of your head — you can't control everything.", "word_hints": {{"masz": "you have", "plecach": "back (loc.)", "możesz": "you can", "wszystkiego": "everything (gen.)", "kontrolować": "to control"}}}}
]
"""

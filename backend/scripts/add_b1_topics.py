"""Insert 6 hand-written B1 grammar topics (articles by the assistant, not Mistral — user
decision 2026-07-29: explanations must be accurate, Mistral only makes practice exercises).
Idempotent: updates by slug if it already exists. Run: python3 scripts/add_b1_topics.py
"""
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "politrain.db")

TOPICS = [
    # slug, title_ru, title_en, order_index, explanation_ru
    ("relative-clauses", "Относительные придаточные (który)", "Relative clauses (który)", 60, """## Суть правила
Слово **który / która / które** («который») соединяет два предложения, заменяя существительное из главного. Главное правило:
- **Род и число** — от слова, к которому относится (антецедента).
- **Падеж** — от роли внутри придаточного (кем/чем który является в своём предложении).

То есть смотри отдельно: род/число берём из главного, падеж — из придаточного.

---

## Таблица: склонение «który» (как прилагательное)
| Падеж | Муж. | Жен. | Ср. | Мн. (не муж.-лич.) | Мн. (муж.-лич.) |
|---|---|---|---|---|---|
| Mianownik (кто/что) | który | która | które | które | którzy |
| Dopełniacz (кого/чего) | którego | której | którego | których | których |
| Celownik (кому) | któremu | której | któremu | którym | którym |
| Biernik (кого/что) | którego* / który | którą | które | które | których |
| Narzędnik (кем) | którym | którą | którym | którymi | którymi |
| Miejscownik (о ком) | którym | której | którym | których | których |

*для одушевлённых муж. рода в Biernik — którego.

---

## Примеры
- To jest człowiek, **który** mieszka obok. — подлежащее → Mianownik.
- Znam kobietę, **którą** widziałeś wczoraj. — прямое дополнение → Biernik (жен.).
- To książka, **o której** ci mówiłem. — после предлога *o* → Miejscownik.
- Mam kolegę, **którego** brat jest lekarzem. — принадлежность → Dopełniacz.

---

## Типичная ошибка
Копируют падеж из главного предложения: ❌ *Człowiek, który znam* → ✅ **Człowiek, którego znam** (który здесь дополнение «которого знаю» → Biernik/Dopełniacz одушевлённого). Запятая перед *który* обязательна."""),

    ("conjunctions", "Союзы и сложные предложения", "Conjunctions & complex sentences", 70, """## Суть правила
Сложное предложение соединяется союзом. Ключевые B1-союзы и что после них:
- **że** — «что» (факт): *Wiem, że masz rację.*
- **żeby / aby** — «чтобы» (цель, желание). Требует особой формы!
- **ponieważ / bo** — «потому что»: *Zostałem, bo padało.*
- **chociaż / mimo że** — «хотя»: *Chociaż było zimno, poszliśmy.*
- **dlatego (że)** — «поэтому / из-за того что».
- **więc** — «поэтому, значит»: *Padało, więc zostałem.*
- **jeśli / jeżeli** — «если»; **kiedy / gdy** — «когда».

---

## że или żeby?
- **że** = сообщаешь факт. Глагол в обычной форме: *Myślę, że to działa.*
- **żeby** = цель или желание. Если подлежащее **то же** — żeby + инфинитив: *Uczę się, żeby zdać.* Если подлежащее **разное** — żeby + форма на -ł с окончанием лица: *Chcę, żebyś przyszedł.* (żebym, żebyś, żeby, żebyśmy, żebyście).

---

## Примеры
- Myślę, **że** to dobry pomysł.
- Robię to, **żeby** ci pomóc. — то же лицо → инфинитив.
- Chcę, **żebyś** mi pomógł. — разные лица → żebyś + pomógł.
- Zostałem w domu, **ponieważ** padało.

---

## Типичная ошибка
Ставят *że* вместо *żeby* для цели: ❌ *Przyszedłem, że pomóc* → ✅ **Przyszedłem, żeby pomóc**. И забывают запятую перед że/żeby/ponieważ/który — она обязательна."""),

    ("verb-prefixes", "Приставки и вид глагола", "Verb prefixes & aspect", 80, """## Суть правила
Приставка делает глагол **совершенного вида** (dokonany) и часто меняет смысл. Несовершенный вид (niedokonany) = процесс/повтор; совершенный = результат/завершённость.

- **czytać → przeczytać** (прочитать до конца)
- **pisać → napisać** (написать), **przepisać** (переписать), **podpisać** (подписать), **zapisać** (записать/сохранить), **wypisać** (выписать)
- **robić → zrobić** (сделать), **przerobić** (переделать)

---

## Частые приставки и их смысл
| Приставка | Смысл | Пример |
|---|---|---|
| po- | немного / начать | poczytać (почитать) |
| prze- | сквозь / пере- / чрезмерно | przeczytać, przepracować |
| wy- | наружу / до конца | wypić (выпить), wyjść |
| za- | начать / закрыть / зайти | zapisać, zamknąć |
| na- | на поверхность / количество | napisać, nazbierać |
| do- | добавить / достичь | dopisać, dojść |
| od- | прочь / обратно | odejść, oddać |

---

## Примеры
- Wczoraj **czytałem** książkę. — процесс (читал).
- Wczoraj **przeczytałem** książkę. — завершил (прочитал).
- Muszę **napisać** e-mail i **podpisać** dokument.

---

## Типичная ошибка
Берут несовершенный вид там, где нужен результат: ❌ *Wczoraj pisałem list i wysłałem* (незавершённо звучит) → ✅ **Wczoraj napisałem list i wysłałem**. Помни: одно завершённое действие → совершенный вид."""),

    ("impersonal", "Безличные конструкции", "Impersonal constructions", 90, """## Суть правила
Безличные конструкции описывают действие без подлежащего. Слово + **инфинитив**:
- **trzeba** — «надо / нужно»
- **można** — «можно»
- **nie wolno** — «нельзя»; **wolno** — «можно/разрешено»
- **warto** — «стоит (имеет смысл)»
- **należy** — «следует» (формально)

Подлежащего нет — «ja», «my» не добавляем.

---

## Настоящее и прошедшее
| Настоящее | Прошедшее (+ było) |
|---|---|
| trzeba kupić | trzeba **było** kupić |
| można wejść | można **było** wejść |
| nie wolno palić | nie **było** wolno palić |
| warto zobaczyć | warto **było** zobaczyć |

Прошедшее образуется добавлением **było** (средний род), а не *był/była*.

---

## Конструкция с «się»
- *Tu **się mówi** po polsku.* — «Здесь говорят по-польски».
- *Jak **się to robi**?* — «Как это делается?»

---

## Примеры
- **Trzeba** kupić chleb.
- Tutaj **można** palić? — Nie, tu **nie wolno**.
- **Warto** było przyjść wcześniej.

---

## Типичная ошибка
Добавляют подлежащее: ❌ *Ja trzeba iść* → ✅ **Trzeba iść** (или *Muszę iść*). И в прошедшем ставят *był* вместо **było**: ❌ *trzeba był* → ✅ **trzeba było**."""),

    ("adverb-comparison", "Степени сравнения наречий", "Comparison of adverbs", 100, """## Суть правила
Наречия (как? — образуются от прилагательных на **-o** или **-e**) имеют три степени:
- сравнительная: **-ej** (часто с чередованием согласной)
- превосходная: **naj-** + сравнительная

*szybko → szybciej → najszybciej.*

---

## Таблица (в т.ч. неправильные)
| Наречие | Сравнит. | Превосх. |
|---|---|---|
| szybko (быстро) | szybciej | najszybciej |
| dobrze (хорошо) | **lepiej** | **najlepiej** |
| źle (плохо) | **gorzej** | **najgorzej** |
| dużo (много) | **więcej** | **najwięcej** |
| mało (мало) | **mniej** | **najmniej** |
| daleko (далеко) | dalej | najdalej |

Для длинных наречий — **bardziej / najbardziej** + наречие: *bardziej interesująco.*

---

## Сравнение: niż / od
- *Biega szybciej **niż** ja.* — niż + именительный (ja).
- *Biega szybciej **ode mnie**.* — od + родительный (mnie).

---

## Примеры
- On gotuje **lepiej niż** ja.
- Ona pracuje **najciężej** w zespole.

---

## Типичная ошибка
Регуляризуют неправильные формы: ❌ *dobrzej* → ✅ **lepiej**; ❌ *dużej* → ✅ **więcej**. И ставят *bardziej* к коротким наречиям: ❌ *bardziej szybko* → ✅ **szybciej**."""),

    ("reported-speech", "Косвенная речь", "Reported speech", 110, """## Суть правила
Косвенная речь передаёт чужие слова через **że** (что), **czy** (ли) или вопросительное слово. Главное отличие от английского: **время НЕ сдвигается** — глагол остаётся в том же времени, что и в прямой речи. Меняются только лица (я→он) по смыслу.

---

## Три типа
| Прямая речь | Косвенная |
|---|---|
| «Jestem zmęczony». | Powiedział, **że jest** zmęczony. |
| «Kupiłem auto». | Powiedział, **że kupił** auto. |
| «Czy masz czas?» | Zapytał, **czy mam** czas. |
| «Gdzie mieszkasz?» | Zapytał, **gdzie mieszkam**. |
| «Przyjdź!» | Powiedział, **żebym przyszedł**. |

- Утверждение → **że**.
- Вопрос да/нет → **czy**.
- Вопрос со словом → то же слово (gdzie, kiedy, dlaczego...).
- Приказ/просьба → **żeby** + форма на -ł.

---

## Примеры
- Ania mówi, **że nie ma** czasu. — «jestem/nie mam» остаётся в настоящем.
- Zapytali, **czy będę** na spotkaniu.
- Poprosił, **żebyśmy** byli cicho.

---

## Типичная ошибка
Сдвигают время как в английском: ❌ *Powiedział, że był zmęczony* (если он и сейчас устал) → ✅ **Powiedział, że jest zmęczony**. И забывают **czy** в вопросах да/нет: ❌ *Zapytał, mam czas* → ✅ **Zapytał, czy mam czas**."""),
]


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    ins = upd = 0
    for slug, title_ru, title_en, order_index, expl in TOPICS:
        c.execute("SELECT id FROM topics WHERE slug=?", (slug,))
        row = c.fetchone()
        if row:
            c.execute("UPDATE topics SET title_ru=?, title_en=?, level_required='B1', "
                      "order_index=?, explanation_ru=? WHERE slug=?",
                      (title_ru, title_en, order_index, expl, slug))
            upd += 1
        else:
            c.execute("INSERT INTO topics (slug, title_ru, title_en, description_ru, description_en, "
                      "level_required, order_index, explanation_ru) "
                      "VALUES (?,?,?,?,?, 'B1', ?, ?)",
                      (slug, title_ru, title_en, title_ru, title_en, order_index, expl))
            ins += 1
    conn.commit()
    c.execute("SELECT COUNT(*) FROM topics WHERE level_required='B1'")
    print(f"B1 topics inserted={ins} updated={upd}; total B1 now={c.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()

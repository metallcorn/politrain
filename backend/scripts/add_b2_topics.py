"""Insert 8 hand-written B2 grammar topics (articles by the assistant, not Mistral — user
decision 2026-07-29/08-03: explanations must be accurate, Mistral only makes practice
exercises). Idempotent: updates by slug. Run: python3 scripts/add_b2_topics.py
"""
import os
import sqlite3

DB = os.path.join(os.path.dirname(__file__), "..", "politrain.db")

TOPICS = [
    ("participles", "Причастия", "Participles", 10, """## Суть правила
Причастие — форма глагола, работающая как прилагательное или деепричастие. В польском их **четыре**:

| Тип | Суффикс | Пример | Роль |
|---|---|---|---|
| Действит. (przymiotnikowy czynny) | **-ący** | czytający (читающий) | как прилагательное, склоняется |
| Страдат. (przymiotnikowy bierny) | **-ny / -ty** | czytany, zrobiony, wzięty | как прилагательное, склоняется |
| Одновременное (współczesny) | **-ąc** | czytając (читая) | как наречие, НЕ склоняется |
| Предшеств. (uprzedni) | **-wszy / -łszy** | przeczytawszy (прочитав) | как наречие, книжное |

---

## Как образовать
- **-ący**: от 3 л. мн. ч. настоящего, *-ą → -ący*: czytają → **czytający**, robią → **robiący**, idą → **idący**. Только от **несовершенного** вида.
- **-ąc**: та же основа + *ąc*: **czytając, robiąc, idąc**. Одно подлежащее, одновременное действие.
- **страдательное**: *-ny* (czytany, pisany, **zrobiony**) или *-ty* (**myty, wzięty, zamknięty**). От обоих видов, склоняется по роду: zrobiony / zrobiona / zrobione.

---

## Примеры
- Człowiek **czytający** gazetę to mój sąsiad. — действит., согласуется с *człowiek*.
- To jest list **napisany** wczoraj. — страдат.
- **Czytając** książkę, piję kawę. — деепричастие, одновременно.

---

## Типичная ошибка
Путают **-ąc** (деепричастие, не склоняется) и **-ący** (прилагательное, склоняется): ❌ *człowiek czytając* → ✅ **człowiek czytający**. И пробуют сделать *-ący* от совершенного вида: ❌ *zrobiący* — такого нет, только *robiący*."""),

    ("passive-voice", "Страдательный залог", "Passive voice", 20, """## Суть правила
Страдательный залог = **być / zostać + страдательное причастие** (-ny/-ty). Выбор вспомогательного глагола зависит от вида:
- **być** — процесс/состояние (несов.): *Dom **jest budowany**.* (дом строится)
- **zostać** — завершённое действие (сов.): *Dom **został zbudowany**.* (дом построили)

Причастие согласуется в роде и числе: zbudowany / zbudowana / zbudowane / zbudowani.

---

## Времена
| | być (процесс) | zostać (результат) |
|---|---|---|
| Наст. | jest pisany | — |
| Прош. | był pisany | został napisany |
| Буд. | będzie pisany | zostanie napisany |

Исполнитель — через **przez + Biernik**: *Książka została napisana **przez** autora.*

---

## Примеры
- List **jest sprawdzany** przez nauczyciela. — процесс.
- Umowa **została podpisana** wczoraj. — результат.
- Zadanie **zostanie wykonane** jutro. — будущее, результат.

---

## Типичная ошибка
Ставят **być** там, где нужен **zostać** для завершённости: ❌ *Dom był zbudowany* (звучит как «был в построенном состоянии») → ✅ **Dom został zbudowany** (действие завершилось). И забывают согласование: ❌ *Umowa został podpisany* → ✅ **została podpisana**."""),

    ("verbal-nouns", "Отглагольные существительные", "Verbal nouns", 30, """## Суть правила
От глагола образуется существительное **среднего рода** (то czytanie), обозначающее действие как понятие. Три суффикса:

| Суффикс | От чего | Пример |
|---|---|---|
| **-anie** | глаголы на -ać | czytać → **czytanie**, pisać → **pisanie** |
| **-enie** | глаголы на -ić/-eć | robić → **robienie**, myśleć → **myślenie** |
| **-cie** | короткие / на -ć, -ąć | pić → **picie**, myć → **mycie**, wziąć → **wzięcie** |

Все — среднего рода, склоняются как *okno*. Вид сохраняется: **czytanie** (процесс) vs **przeczytanie** (завершение).

---

## Примеры
- **Palenie** jest szkodliwe. — курение вредно.
- Lubię **czytanie** książek. — люблю чтение книг.
- Po **przeczytaniu** listu wyszedł. — после прочтения письма.

---

## Типичная ошибка
Берут неправильный суффикс: ❌ *robanie* → ✅ **robienie**; ❌ *pijenie* → ✅ **picie**. И забывают, что род **средний**: *to ciekawe czytanie*, не *ten*."""),

    ("complex-conditional", "Сложное и нереальное условие", "Complex & unreal conditionals", 40, """## Суть правила
Различай **реальное** и **нереальное** условие — у них разные союзы:
- **Реальное** (возможно) → **jeśli / jeżeli** + будущее: *Jeśli będę miał czas, przyjdę.* (если будет время — приду)
- **Нереальное** (гипотеза, мечта, сожаление) → **gdyby** + форма на -ł: *Gdybym miał czas, przyszedłbym.* (если бы было время — пришёл бы)

Частица **-by** прикрепляется к **gdyby**, а не к jeśli.

---

## Формы gdyby
gdyby**m**, gdyby**ś**, gdyby, gdyby**śmy**, gdyby**ście**, gdyby + глагол на -ł.

- Настоящее/будущее нереальное: *Gdybym był bogaty, kupiłbym dom.*
- Прошедшее нереальное (сожаление): *Gdybym **wiedział**, nie **zrobiłbym** tego.* (если бы знал — не сделал бы)
- Книжная форма «zaprzeszła» с *był*: *Gdybym był wiedział…* — литературно, редко в речи.

---

## Примеры
- **Na twoim miejscu** bym odpoczął. — на твоём месте я бы отдохнул.
- **Gdyby** nie deszcz, poszlibyśmy na spacer.

---

## Типичная ошибка
Смешивают реальное и нереальное: ❌ *Jeśli bym miał czas* → ✅ **Gdybym miał czas** (нереальное) или **Jeśli będę miał czas** (реальное). Частица -by идёт с *gdyby*, не с *jeśli*."""),

    ("word-formation", "Словообразование", "Word formation", 50, """## Суть правила
Зная суффиксы, можно **угадать смысл** незнакомого слова и строить свои. Самые продуктивные:

| Суффикс | Значение | Род | Пример |
|---|---|---|---|
| **-ość** | абстрактное понятие | ж. | wolny → **wolność**, radość, możliwość |
| **-arz** | деятель | м. | piekarz (пекарь), pisarz, malarz |
| **-nik** | деятель / предмет | м. | pracownik, ogrodnik, słownik |
| **-ka** | женский род / уменьш. | ж. | nauczyciel → **nauczycielka** |
| **-owy / -ny** | прилагательное | — | dom → **domowy**, samochód → samochodowy |

Приставка **nie-** — отрицание: możliwy → **niemożliwy**.

---

## Примеры
- *wolność, ciekawość, prędkość* — все на **-ość**, все женского рода.
- *piekarz* печёт, *pisarz* пишет, *malarz* красит/рисует.

---

## Типичная ошибка
Ошибаются в роде: **-ość** ВСЕГДА женский — *ta wolność*, не *ten wolność*. И калькируют: не любое действие даёт деятеля на *-arz*."""),

    ("collocations", "Устойчивые сочетания", "Collocations", 60, """## Суть правила
Коллокация — слова, которые «дружат» в польском. Важно, **какой глагол** идёт с существительным — дословный перевод часто звучит неестественно.

| По-русски | Правильно по-польски |
|---|---|
| обращать внимание | **zwracać uwagę** |
| принимать участие | **brać / wziąć udział** |
| принять решение | **podjąć decyzję** |
| совершить ошибку | **popełnić błąd** |
| добиться успеха | **odnieść sukces** |
| иметь влияние на | **mieć wpływ na** |
| сдержать слово | **dotrzymać słowa** |
| нести ответственность | **ponosić odpowiedzialność** |

---

## Примеры
- Muszę **podjąć decyzję** do jutra.
- On zawsze **dotrzymuje słowa**.
- **Zwróć uwagę** na szczegóły.

---

## Типичная ошибка
Калькируют глагол из русского/английского: ❌ *robić decyzję* («делать решение») → ✅ **podjąć decyzję**; ❌ *robić błąd* → ✅ **popełnić błąd**; ❌ *mieć sukces* → ✅ **odnieść sukces**."""),

    ("formal-register", "Формальный стиль", "Formal register", 70, """## Суть правила
К незнакомым, официальным лицам, в письмах — **формальный стиль**. Обращение на «вы» = **Pan / Pani + глагол в 3-м лице** (не «ty»).

- *Czy **mógłby Pan** mi pomóc?* — Не могли бы вы мне помочь? (мужчине)
- *Czy **mogłaby Pani** powtórzyć?* — (женщине)

Вежливые обороты: **uprzejmie proszę**, **czy byłby Pan tak uprzejmy**, **chciałbym prosić o…**

---

## Письмо
- Начало: **Szanowny Panie / Szanowna Pani**
- Конец: **Z poważaniem** (с уважением) / **Z wyrazami szacunku**
- Официальная лексика: *należy, w związku z, uprzejmie informuję, zobowiązuję się.*

---

## Примеры
- Неформально: *Cześć! Możesz mi pomóc?*
- Формально: *Dzień dobry, czy **mógłby Pan** mi pomóc?*

---

## Типичная ошибка
Обращаются на «ty» к чиновнику/незнакомцу: ❌ *Możesz mi pomóc?* → ✅ **Czy mógłby Pan mi pomóc?** И после *Pan/Pani* ставят глагол во 2-м лице: ❌ *Pan możesz* → ✅ **Pan może**."""),

    ("aspect-advanced", "Тонкости вида глагола", "Advanced aspect", 80, """## Суть правила
За пределами базовых пар (robić/zrobić) есть более тонкие случаи:

- **Двувидовые** (dwuaspektowe) — один глагол, оба вида, вид ясен из контекста: *kazać, potrafić, aresztować, awizować.*
- **Многократные** (wielokrotne) — привычное, повторяющееся долго: **bywać** (бывать), **jadać** (едать), **sypiać** (сыпать/спать обычно), **czytywać, pisywać**. *Bywam w kinie.* — время от времени хожу в кино.
- **Начинательные** (za-) — начало/единичный порыв: **zapłakać** (заплакать), **zaśpiewać** (запеть), **zachorować** (заболеть).

---

## Оттенки совершенного вида
- результат: **zrobić**
- мгновенность: **krzyknąć** (крикнуть один раз)
- «немного, недолго» (po-): **poczytać** (почитать чуть-чуть), **pospać.**

---

## Примеры
- **Jadam** obiady w tej restauracji. — регулярно обедаю (многократное).
- Nagle **zaśpiewał**. — вдруг запел (начинательное).
- **Poczytałem** godzinę i poszedłem spać. — почитал часок.

---

## Типичная ошибка
Берут простой несовершенный там, где смысл «время от времени годами» — тогда лучше многократный: *chodzę* (иду/хожу вообще) vs **chadzam** (захаживаю). И путают начало действия (zaśpiewać) с завершением."""),
]


def main():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    ins = upd = 0
    for slug, title_ru, title_en, order_index, expl in TOPICS:
        c.execute("SELECT id FROM topics WHERE slug=?", (slug,))
        if c.fetchone():
            c.execute("UPDATE topics SET title_ru=?, title_en=?, level_required='B2', "
                      "order_index=?, explanation_ru=? WHERE slug=?",
                      (title_ru, title_en, order_index, expl, slug))
            upd += 1
        else:
            c.execute("INSERT INTO topics (slug, title_ru, title_en, description_ru, description_en, "
                      "level_required, order_index, explanation_ru) VALUES (?,?,?,?,?, 'B2', ?, ?)",
                      (slug, title_ru, title_en, title_ru, title_en, order_index, expl))
            ins += 1
    conn.commit()
    c.execute("SELECT COUNT(*) FROM topics WHERE level_required='B2'")
    print(f"B2 topics inserted={ins} updated={upd}; total B2 now={c.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()

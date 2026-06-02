"""Seed initial data: topics, vocabulary, achievements."""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, engine, Base
import models

Base.metadata.create_all(bind=engine)


TOPICS = [
    # A0
    {"slug": "alphabet", "title_ru": "Алфавит и произношение", "title_en": "Alphabet and Pronunciation",
     "description_ru": "Польский алфавит, специфические буквы и звуки", "description_en": "Polish alphabet, specific letters and sounds",
     "level_required": "A0", "order_index": 1},
    {"slug": "greetings", "title_ru": "Приветствия и базовые фразы", "title_en": "Greetings and Basic Phrases",
     "description_ru": "Как здороваться, прощаться и представляться", "description_en": "How to greet, say goodbye and introduce yourself",
     "level_required": "A0", "order_index": 2},
    {"slug": "numbers", "title_ru": "Числа 1-100", "title_en": "Numbers 1-100",
     "description_ru": "Польские числительные от 1 до 100", "description_en": "Polish numbers from 1 to 100",
     "level_required": "A0", "order_index": 3},
    {"slug": "colors", "title_ru": "Цвета и базовые прилагательные", "title_en": "Colors and Basic Adjectives",
     "description_ru": "Основные цвета и прилагательные", "description_en": "Main colors and adjectives",
     "level_required": "A0", "order_index": 4},
    {"slug": "days-months", "title_ru": "Дни недели и месяцы", "title_en": "Days of the Week and Months",
     "description_ru": "Дни недели, месяцы и базовые временные выражения", "description_en": "Days, months and basic time expressions",
     "level_required": "A0", "order_index": 5},

    # A1
    {"slug": "pronouns", "title_ru": "Личные местоимения", "title_en": "Personal Pronouns",
     "description_ru": "Ja, ty, on, ona, ono, my, wy, oni, one", "description_en": "Ja, ty, on, ona, ono, my, wy, oni, one",
     "level_required": "A1", "order_index": 6},
    {"slug": "verb-byc", "title_ru": "Глагол 'być' (быть)", "title_en": "Verb 'być' (to be)",
     "description_ru": "Спряжение глагола być в настоящем времени", "description_en": "Conjugation of być in present tense",
     "level_required": "A1", "order_index": 7},
    {"slug": "present-tense", "title_ru": "Настоящее время глаголов", "title_en": "Present Tense of Verbs",
     "description_ru": "Глаголы на -ać, -ić, -yć в настоящем времени", "description_en": "Verbs ending in -ać, -ić, -yć in present tense",
     "level_required": "A1", "order_index": 8},
    {"slug": "nominative", "title_ru": "Именительный падеж (Mianownik)", "title_en": "Nominative Case (Mianownik)",
     "description_ru": "Именительный падеж существительных и прилагательных", "description_en": "Nominative case of nouns and adjectives",
     "level_required": "A1", "order_index": 9},
    {"slug": "genitive", "title_ru": "Родительный падеж (Dopełniacz)", "title_en": "Genitive Case (Dopełniacz)",
     "description_ru": "Родительный падеж: отрицание, принадлежность, количество", "description_en": "Genitive: negation, possession, quantity",
     "level_required": "A1", "order_index": 10},
    {"slug": "questions", "title_ru": "Базовые вопросы", "title_en": "Basic Questions",
     "description_ru": "Kto? Co? Gdzie? Kiedy? Jak? Dlaczego?", "description_en": "Kto? Co? Gdzie? Kiedy? Jak? Dlaczego?",
     "level_required": "A1", "order_index": 11},

    # A2
    {"slug": "accusative", "title_ru": "Винительный падеж (Biernik)", "title_en": "Accusative Case (Biernik)",
     "description_ru": "Прямое дополнение, после глаголов движения", "description_en": "Direct object, after movement verbs",
     "level_required": "A2", "order_index": 12},
    {"slug": "dative", "title_ru": "Дательный падеж (Celownik)", "title_en": "Dative Case (Celownik)",
     "description_ru": "Косвенное дополнение, кому/чему", "description_en": "Indirect object, to whom/what",
     "level_required": "A2", "order_index": 13},
    {"slug": "past-tense", "title_ru": "Прошедшее время", "title_en": "Past Tense",
     "description_ru": "Образование прошедшего времени глаголов", "description_en": "Formation of past tense verbs",
     "level_required": "A2", "order_index": 14},
    {"slug": "future-tense", "title_ru": "Будущее время", "title_en": "Future Tense",
     "description_ru": "Простое и сложное будущее время", "description_en": "Simple and compound future tense",
     "level_required": "A2", "order_index": 15},
    {"slug": "adjective-comparison", "title_ru": "Степени сравнения прилагательных", "title_en": "Adjective Comparison",
     "description_ru": "Сравнительная и превосходная степень", "description_en": "Comparative and superlative degrees",
     "level_required": "A2", "order_index": 16},
    {"slug": "numbers-dates", "title_ru": "Числительные и даты", "title_en": "Numbers and Dates",
     "description_ru": "Порядковые числительные, даты, годы", "description_en": "Ordinal numbers, dates, years",
     "level_required": "A2", "order_index": 17},

    # B1
    {"slug": "instrumental", "title_ru": "Творительный падеж (Narzędnik)", "title_en": "Instrumental Case (Narzędnik)",
     "description_ru": "Орудие действия, с кем/чем, профессии", "description_en": "Tool/means, with whom/what, professions",
     "level_required": "B1", "order_index": 18},
    {"slug": "locative", "title_ru": "Местный падеж (Miejscownik)", "title_en": "Locative Case (Miejscownik)",
     "description_ru": "О чём говорим, где находимся", "description_en": "What we talk about, where we are",
     "level_required": "B1", "order_index": 19},
    {"slug": "vocative", "title_ru": "Звательный падеж (Wołacz)", "title_en": "Vocative Case (Wołacz)",
     "description_ru": "Обращение к кому-либо", "description_en": "Direct address",
     "level_required": "B1", "order_index": 20},
    {"slug": "conditional", "title_ru": "Условное наклонение", "title_en": "Conditional Mood",
     "description_ru": "Tryb warunkowy: chciałbym, gdybym...", "description_en": "Tryb warunkowy: chciałbym, gdybym...",
     "level_required": "B1", "order_index": 21},
    {"slug": "motion-verbs", "title_ru": "Глаголы движения", "title_en": "Motion Verbs",
     "description_ru": "Iść, jechać, chodzić, jeździć и их приставки", "description_en": "Iść, jechać, chodzić, jeździć and their prefixes",
     "level_required": "B1", "order_index": 22},
    {"slug": "aspect", "title_ru": "Вид глагола (совершенный/несовершенный)", "title_en": "Verb Aspect (perfective/imperfective)",
     "description_ru": "Разница между видами глагола", "description_en": "Difference between verb aspects",
     "level_required": "B1", "order_index": 23},
]

VOCABULARY = [
    # A0 - Greetings
    {"polish": "cześć", "translation_ru": "привет", "translation_en": "hi", "example_sentence": "Cześć, jak się masz?", "level": "A0", "topic_slug": "greetings"},
    {"polish": "dzień dobry", "translation_ru": "добрый день", "translation_en": "good day", "example_sentence": "Dzień dobry, jak się Pan miewa?", "level": "A0", "topic_slug": "greetings"},
    {"polish": "do widzenia", "translation_ru": "до свидания", "translation_en": "goodbye", "example_sentence": "Do widzenia! Do zobaczenia jutro.", "level": "A0", "topic_slug": "greetings"},
    {"polish": "dziękuję", "translation_ru": "спасибо", "translation_en": "thank you", "example_sentence": "Dziękuję za pomoc.", "level": "A0", "topic_slug": "greetings"},
    {"polish": "przepraszam", "translation_ru": "извините / прошу прощения", "translation_en": "excuse me / sorry", "example_sentence": "Przepraszam, gdzie jest toaleta?", "level": "A0", "topic_slug": "greetings"},
    {"polish": "proszę", "translation_ru": "пожалуйста", "translation_en": "please / here you are", "example_sentence": "Proszę, to dla ciebie.", "level": "A0", "topic_slug": "greetings"},
    {"polish": "tak", "translation_ru": "да", "translation_en": "yes", "example_sentence": "Tak, masz rację.", "level": "A0", "topic_slug": "greetings"},
    {"polish": "nie", "translation_ru": "нет / не", "translation_en": "no / not", "example_sentence": "Nie, to nieprawda.", "level": "A0", "topic_slug": "greetings"},

    # A0 - Numbers
    {"polish": "jeden/jedna", "translation_ru": "один/одна", "translation_en": "one", "example_sentence": "Mam jedną siostrę.", "level": "A0", "topic_slug": "numbers"},
    {"polish": "dwa/dwie", "translation_ru": "два/две", "translation_en": "two", "example_sentence": "Mam dwa koty.", "level": "A0", "topic_slug": "numbers"},
    {"polish": "trzy", "translation_ru": "три", "translation_en": "three", "example_sentence": "Trzy kawy poproszę.", "level": "A0", "topic_slug": "numbers"},
    {"polish": "pięć", "translation_ru": "пять", "translation_en": "five", "example_sentence": "Mam pięć minut.", "level": "A0", "topic_slug": "numbers"},
    {"polish": "dziesięć", "translation_ru": "десять", "translation_en": "ten", "example_sentence": "Za dziesięć minut będę.", "level": "A0", "topic_slug": "numbers"},

    # A0 - Colors
    {"polish": "czerwony", "translation_ru": "красный", "translation_en": "red", "example_sentence": "Mam czerwony samochód.", "level": "A0", "topic_slug": "colors"},
    {"polish": "niebieski", "translation_ru": "синий / голубой", "translation_en": "blue", "example_sentence": "Niebo jest niebieskie.", "level": "A0", "topic_slug": "colors"},
    {"polish": "zielony", "translation_ru": "зелёный", "translation_en": "green", "example_sentence": "Trawa jest zielona.", "level": "A0", "topic_slug": "colors"},
    {"polish": "biały", "translation_ru": "белый", "translation_en": "white", "example_sentence": "Śnieg jest biały.", "level": "A0", "topic_slug": "colors"},
    {"polish": "czarny", "translation_ru": "чёрный", "translation_en": "black", "example_sentence": "Mam czarny kot.", "level": "A0", "topic_slug": "colors"},

    # A1
    {"polish": "dom", "translation_ru": "дом", "translation_en": "house", "example_sentence": "Mieszkam w dużym domu.", "level": "A1", "topic_slug": "nominative"},
    {"polish": "rodzina", "translation_ru": "семья", "translation_en": "family", "example_sentence": "Moja rodzina jest duża.", "level": "A1", "topic_slug": "nominative"},
    {"polish": "praca", "translation_ru": "работа", "translation_en": "work", "example_sentence": "Idę do pracy o ósmej.", "level": "A1", "topic_slug": "nominative"},
    {"polish": "szkoła", "translation_ru": "школа", "translation_en": "school", "example_sentence": "Ona idzie do szkoły.", "level": "A1", "topic_slug": "nominative"},
    {"polish": "jeść", "translation_ru": "есть / кушать", "translation_en": "to eat", "example_sentence": "Jem śniadanie o siódmej.", "level": "A1", "topic_slug": "present-tense"},
    {"polish": "pić", "translation_ru": "пить", "translation_en": "to drink", "example_sentence": "Lubię pić kawę rano.", "level": "A1", "topic_slug": "present-tense"},
    {"polish": "mówić", "translation_ru": "говорить", "translation_en": "to speak", "example_sentence": "Mówię po polsku trochę.", "level": "A1", "topic_slug": "present-tense"},
    {"polish": "rozumieć", "translation_ru": "понимать", "translation_en": "to understand", "example_sentence": "Nie rozumiem tego słowa.", "level": "A1", "topic_slug": "present-tense"},
    {"polish": "lubić", "translation_ru": "любить / нравится", "translation_en": "to like", "example_sentence": "Lubię muzykę i filmy.", "level": "A1", "topic_slug": "present-tense"},

    # A2
    {"polish": "kupować", "translation_ru": "покупать", "translation_en": "to buy", "example_sentence": "Kupuję chleb w sklepie.", "level": "A2", "topic_slug": "accusative"},
    {"polish": "widzieć", "translation_ru": "видеть", "translation_en": "to see", "example_sentence": "Widzę piękny zachód słońca.", "level": "A2", "topic_slug": "accusative"},
    {"polish": "wczoraj", "translation_ru": "вчера", "translation_en": "yesterday", "example_sentence": "Wczoraj byłem w kinie.", "level": "A2", "topic_slug": "past-tense"},
    {"polish": "jutro", "translation_ru": "завтра", "translation_en": "tomorrow", "example_sentence": "Jutro pojadę do Krakowa.", "level": "A2", "topic_slug": "future-tense"},
    {"polish": "może", "translation_ru": "может быть / можно", "translation_en": "maybe / can", "example_sentence": "Może jutro pójdziemy razem.", "level": "A2", "topic_slug": "future-tense"},

    # B1
    {"polish": "chciałbym/chciałabym", "translation_ru": "я хотел бы / я хотела бы", "translation_en": "I would like", "example_sentence": "Chciałbym zamówić stolik.", "level": "B1", "topic_slug": "conditional"},
    {"polish": "gdyby", "translation_ru": "если бы", "translation_en": "if (conditional)", "example_sentence": "Gdyby miał czas, przyszedłby.", "level": "B1", "topic_slug": "conditional"},
    {"polish": "pomimo że", "translation_ru": "несмотря на то что", "translation_en": "despite the fact that", "example_sentence": "Pomimo że był zmęczony, pracował.", "level": "B1", "topic_slug": "aspect"},
    {"polish": "jednak", "translation_ru": "однако / тем не менее", "translation_en": "however / nevertheless", "example_sentence": "Chciałem iść, jednak zostałem.", "level": "B1", "topic_slug": "aspect"},
]

EXERCISES = [
    # Greetings exercises
    {
        "type": "multiple_choice", "level": "A0", "topic_slug": "greetings",
        "question": "Как сказать 'привет' по-польски?",
        "correct_answer": "cześć",
        "options": json.dumps(["cześć", "dziękuję", "przepraszam", "do widzenia"]),
        "explanation": "'Cześć' — неформальное приветствие, используется между друзьями",
    },
    {
        "type": "fill_blank", "level": "A0", "topic_slug": "greetings",
        "question": "___, jak się masz? (Привет, как дела?)",
        "correct_answer": "Cześć",
        "hint": "неформальное приветствие",
        "explanation": "'Cześć' используется в неформальной обстановке",
    },
    {
        "type": "translate", "level": "A0", "topic_slug": "greetings",
        "question": "Переведи на польский: 'Спасибо большое'",
        "correct_answer": "Dziękuję bardzo",
        "explanation": "'Dziękuję' = спасибо, 'bardzo' = очень/большое",
    },

    # Numbers
    {
        "type": "multiple_choice", "level": "A0", "topic_slug": "numbers",
        "question": "Как будет число '7' по-польски?",
        "correct_answer": "siedem",
        "options": json.dumps(["sześć", "siedem", "osiem", "dziewięć"]),
        "explanation": "7 = siedem, 6 = sześć, 8 = osiem, 9 = dziewięć",
    },
    {
        "type": "fill_blank", "level": "A0", "topic_slug": "numbers",
        "question": "Mam ___ (три) koty.",
        "correct_answer": "trzy",
        "explanation": "trzy = три (для существительных множественного числа 3-4)",
    },

    # Present tense
    {
        "type": "fill_blank", "level": "A1", "topic_slug": "present-tense",
        "question": "Ona ___ (czytać) książkę.",
        "correct_answer": "czyta",
        "hint": "3-е лицо единственное число",
        "explanation": "czytać → czyta (3 л. ед. ч.)",
    },
    {
        "type": "multiple_choice", "level": "A1", "topic_slug": "present-tense",
        "question": "Ja ___ (mówić) po polsku.",
        "correct_answer": "mówię",
        "options": json.dumps(["mówię", "mówisz", "mówi", "mówimy"]),
        "explanation": "mówić: ja mówię, ty mówisz, on/ona mówi",
    },
    {
        "type": "order_words", "level": "A1", "topic_slug": "present-tense",
        "question": "Составь предложение: [lubię / bardzo / muzykę / Ja]",
        "correct_answer": "Ja lubię bardzo muzykę",
        "explanation": "Стандартный порядок: подлежащее + глагол + наречие + дополнение",
    },

    # Verb być
    {
        "type": "fill_blank", "level": "A1", "topic_slug": "verb-byc",
        "question": "Ty ___ moim przyjacielem. (Ты мой друг.)",
        "correct_answer": "jesteś",
        "hint": "być, 2-е лицо ед. ч.",
        "explanation": "być: jestem, jesteś, jest, jesteśmy, jesteście, są",
    },
    {
        "type": "multiple_choice", "level": "A1", "topic_slug": "verb-byc",
        "question": "Oni ___ w domu.",
        "correct_answer": "są",
        "options": json.dumps(["jest", "jestem", "są", "jesteś"]),
        "explanation": "Для oni/one (они) — są",
    },

    # Genitive
    {
        "type": "fill_blank", "level": "A1", "topic_slug": "genitive",
        "question": "Nie mam ___ (czas — время).",
        "correct_answer": "czasu",
        "hint": "после отрицания — родительный падеж",
        "explanation": "После отрицания nie используется родительный падеж: czas → czasu",
    },

    # Accusative
    {
        "type": "fill_blank", "level": "A2", "topic_slug": "accusative",
        "question": "Lubię ___ (kawa — кофе, ж.р.).",
        "correct_answer": "kawę",
        "hint": "бiernik женского рода",
        "explanation": "После lubić нужен бiernik: kawa → kawę",
    },
    {
        "type": "multiple_choice", "level": "A2", "topic_slug": "accusative",
        "question": "Mam ___ (brat).",
        "correct_answer": "brata",
        "options": json.dumps(["brat", "brata", "bracie", "bratem"]),
        "explanation": "Mam требует бiernik. Одушевлённые мужского рода: brat → brata",
    },

    # Past tense
    {
        "type": "fill_blank", "level": "A2", "topic_slug": "past-tense",
        "question": "Wczoraj ja (m) ___ (iść) do sklepu.",
        "correct_answer": "szedłem",
        "hint": "прошедшее время мужского рода, я",
        "explanation": "iść в прошедшем: szedłem (m) / szłam (f)",
    },

    # Conditional
    {
        "type": "fill_blank", "level": "B1", "topic_slug": "conditional",
        "question": "___ pojechać do Paryża. (Я хотел бы поехать в Париж.)",
        "correct_answer": "Chciałbym",
        "hint": "условное наклонение, мужской род",
        "explanation": "chcieć + by → chciałbym (м.р.) / chciałabym (ж.р.)",
    },
]

ACHIEVEMENTS = [
    {"slug": "first_lesson", "title_ru": "Первый шаг", "title_en": "First Step",
     "description_ru": "Завершить первый урок", "description_en": "Complete the first lesson",
     "icon": "🎯", "xp_reward": 50, "condition_type": "first_lesson", "condition_value": 1},
    {"slug": "week_streak", "title_ru": "Неделя подряд", "title_en": "Week Streak",
     "description_ru": "7 дней streak", "description_en": "7-day streak",
     "icon": "🔥", "xp_reward": 100, "condition_type": "streak", "condition_value": 7},
    {"slug": "month_streak", "title_ru": "Месяц подряд", "title_en": "Month Streak",
     "description_ru": "30 дней streak", "description_en": "30-day streak",
     "icon": "🏆", "xp_reward": 500, "condition_type": "streak", "condition_value": 30},
    {"slug": "vocab_100", "title_ru": "Сотня слов", "title_en": "Hundred Words",
     "description_ru": "100 слов в словаре", "description_en": "100 words in vocabulary",
     "icon": "📚", "xp_reward": 100, "condition_type": "vocab_count", "condition_value": 100},
    {"slug": "vocab_500", "title_ru": "Пятьсот слов", "title_en": "Five Hundred Words",
     "description_ru": "500 слов в словаре", "description_en": "500 words in vocabulary",
     "icon": "📖", "xp_reward": 300, "condition_type": "vocab_count", "condition_value": 500},
    {"slug": "chat_starter", "title_ru": "Разговорчивый", "title_en": "Talkative",
     "description_ru": "10 сообщений в чате", "description_en": "10 chat messages",
     "icon": "💬", "xp_reward": 50, "condition_type": "chat_messages", "condition_value": 10},
    {"slug": "chat_100", "title_ru": "Болтун", "title_en": "Chatterbox",
     "description_ru": "100 сообщений в чате", "description_en": "100 chat messages",
     "icon": "🗣️", "xp_reward": 200, "condition_type": "chat_messages", "condition_value": 100},
    {"slug": "xp_1000", "title_ru": "Тысячник", "title_en": "Thousand XP",
     "description_ru": "Набрать 1000 XP", "description_en": "Earn 1000 XP",
     "icon": "⚡", "xp_reward": 100, "condition_type": "xp", "condition_value": 1000},
]


def seed():
    db = SessionLocal()
    try:
        # Topics
        topic_map = {}
        for t in TOPICS:
            existing = db.query(models.Topic).filter(models.Topic.slug == t["slug"]).first()
            if not existing:
                topic = models.Topic(**{k: v for k, v in t.items()})
                db.add(topic)
                db.flush()
                topic_map[t["slug"]] = topic.id
            else:
                topic_map[t["slug"]] = existing.id
        db.commit()

        # Re-fetch map
        for t in TOPICS:
            topic = db.query(models.Topic).filter(models.Topic.slug == t["slug"]).first()
            topic_map[t["slug"]] = topic.id

        # Vocabulary
        for v in VOCABULARY:
            topic_slug = v.pop("topic_slug", None)
            topic_id = topic_map.get(topic_slug) if topic_slug else None
            existing = db.query(models.Vocabulary).filter(
                models.Vocabulary.polish == v["polish"]
            ).first()
            if not existing:
                vocab = models.Vocabulary(**v, topic_id=topic_id)
                db.add(vocab)
            v["topic_slug"] = topic_slug  # restore
        db.commit()

        # Exercises
        for e in EXERCISES:
            topic_slug = e.pop("topic_slug", None)
            topic_id = topic_map.get(topic_slug) if topic_slug else None
            existing = db.query(models.Exercise).filter(
                models.Exercise.question == e["question"]
            ).first()
            if not existing:
                ex = models.Exercise(**e, topic_id=topic_id)
                db.add(ex)
            e["topic_slug"] = topic_slug  # restore
        db.commit()

        # Achievements
        for a in ACHIEVEMENTS:
            existing = db.query(models.Achievement).filter(
                models.Achievement.slug == a["slug"]
            ).first()
            if not existing:
                ach = models.Achievement(**a)
                db.add(ach)
        db.commit()

        print("Seed completed successfully!")

    finally:
        db.close()


if __name__ == "__main__":
    seed()

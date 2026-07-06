"""Language plumbing for a multi-lingual user base (users are NOT guaranteed to be
Russian-speaking).

Two jobs:
1. lang_name(code) — prompts are written in English meta-language and receive a full
   language NAME in {native_language}; passing a raw code ("ru") makes Mistral answer
   in English. Every prompt .format() call site must go through lang_name().
2. ui(key, lang) — the few user-facing strings the BACKEND generates itself (exercise
   question stems, badges). Add languages by extending the inner dicts; unknown
   languages fall back to English.
"""

_LANG_NAMES = {
    "ru": "Russian",
    "en": "English",
    "uk": "Ukrainian",
    "be": "Belarusian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "pl": "Polish",
}


def lang_name(code: str) -> str:
    """Full English name of a language for prompt templates; unknown codes pass through."""
    return _LANG_NAMES.get((code or "").lower(), code or "English")


_UI = {
    "assemble_word": {
        "ru": "Собери слово по-польски: {translation}",
        "en": "Assemble the Polish word for: {translation}",
    },
    "idioms_badge": {
        "ru": "Идиомы",
        "en": "Idioms",
    },
    "debrief_no_messages": {
        "ru": "Ты ещё ничего не написал — напиши пару реплик, и я разберу!",
        "en": "You haven't written anything yet — send a few lines and I'll review them!",
    },
    "debrief_failed": {
        "ru": "Не удалось собрать разбор — попробуй ещё раз чуть позже.",
        "en": "Couldn't build the debrief — please try again in a moment.",
    },
    "dialogue_fallback_title": {
        "ru": "диалог",
        "en": "dialogue",
    },
    "ai_unavailable": {
        "ru": "AI временно недоступен.",
        "en": "AI is temporarily unavailable.",
    },
    "ai_unavailable_topic": {
        "ru": "**{title}**\n\nAI временно недоступен. Используйте упражнения для изучения темы.",
        "en": "**{title}**\n\nAI is temporarily unavailable. Use the exercises to study the topic.",
    },
    "chat_topics": {
        "ru": ["Расскажи о своём дне", "Опиши свой город", "Что ты делал на выходных?",
               "Поговорим о еде", "Твои планы на будущее", "Свободная тема"],
        "en": ["Tell me about your day", "Describe your city", "What did you do on the weekend?",
               "Let's talk about food", "Your plans for the future", "Free topic"],
    },
}


def ui(key: str, lang: str, **kwargs):
    """Server-generated user-facing string (or list) in the user's language (en fallback)."""
    variants = _UI[key]
    template = variants.get((lang or "").lower(), variants["en"])
    if isinstance(template, str) and kwargs:
        return template.format(**kwargs)
    return template

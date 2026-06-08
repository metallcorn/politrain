#!/usr/bin/env python3
"""Normalize learn-word vocabulary to dictionary (lemma) form and deduplicate.

Words added via the in-exercise word-tap (POST /vocabulary/learn-word) are stored in
whatever inflected form appeared in the sentence (e.g. "bieli", "przeciwieństwem").
This maintenance script:
  1. Finds learn-word entries (translation_en == '' — that's how learn-word marks them).
  2. Asks Mistral for the dictionary lemma + a dictionary-form translation.
  3. If the lemma already exists as another Vocabulary row → migrates the user's progress
     (UserVocabulary) onto the canonical row and deletes the inflected duplicate (Python dedup).
  4. Otherwise rewrites the entry in place to the lemma form (and fills translation_en).

Run from backend/ with the env loaded, e.g.:
    env $(cat ../.env | grep -v '^#' | xargs) venv/bin/python3 scripts/normalize_vocab.py
Add --dry-run to preview without writing.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services import mistral

DRY_RUN = "--dry-run" in sys.argv

_LEMMA_PROMPT = (
    "Ты лингвист польского языка. Дано польское слово в произвольной форме и его перевод.\n"
    "Верни словарную (начальную) форму слова и её перевод на русский в словарной форме.\n"
    "Словарная форма: существительное — именительный падеж ед.ч.; глагол — инфинитив; "
    "прилагательное — мужской род ед.ч.; наречие оставь как есть.\n"
    "Если слово УЖЕ в словарной форме — верни его без изменений.\n\n"
    "Слово: {word}\nТекущий перевод: {translation}\n\n"
    "Ответь ТОЛЬКО валидным JSON без markdown:\n"
    '{{"lemma": "<словарная форма польского слова>", "translation_ru": "<перевод>", '
    '"translation_en": "<English translation>", "already_base": true|false}}'
)


async def lemmatize(word: str, translation: str) -> dict | None:
    try:
        raw = await mistral.simple_prompt(
            system="You are a Polish lexicographer. Respond only with a valid JSON object.",
            user=_LEMMA_PROMPT.format(word=word, translation=translation),
            temperature=0.2, max_tokens=200, timeout=20.0, retries=1,
            model="mistral-small-latest",
        )
        return await mistral.parse_json_response(raw)
    except Exception as e:
        print(f"  ! Mistral failed for {word!r}: {e}")
        return None


def migrate_and_delete(db, dup: models.Vocabulary, canonical_id: int):
    """Move the user's progress from a duplicate vocab row onto the canonical row, then delete the dup."""
    uvs = db.query(models.UserVocabulary).filter(models.UserVocabulary.vocab_id == dup.id).all()
    for uv in uvs:
        existing = db.query(models.UserVocabulary).filter(
            models.UserVocabulary.user_id == uv.user_id,
            models.UserVocabulary.vocab_id == canonical_id,
        ).first()
        if existing:
            # User already has the canonical word — keep the stronger streak, drop the duplicate link
            if (uv.correct_streak or 0) > (existing.correct_streak or 0):
                existing.correct_streak = uv.correct_streak
                existing.next_review = uv.next_review
            db.delete(uv)
        else:
            uv.vocab_id = canonical_id
    db.delete(dup)


async def main():
    db = SessionLocal()
    entries = db.query(models.Vocabulary).filter(
        (models.Vocabulary.translation_en == "") | (models.Vocabulary.translation_en.is_(None))
    ).all()
    print(f"learn-word entries to check: {len(entries)}{'  (DRY RUN)' if DRY_RUN else ''}")

    normalized = deduped = unchanged = 0
    for v in entries:
        res = await lemmatize(v.polish, v.translation_ru)
        if not res:
            continue
        lemma = (res.get("lemma") or "").strip()
        if not lemma:
            continue

        if lemma.lower() == v.polish.strip().lower():
            # already dictionary form — just backfill translation_en if missing
            if not v.translation_en and res.get("translation_en"):
                print(f"  = {v.polish!r}: already base, filling translation_en")
                if not DRY_RUN:
                    v.translation_en = res.get("translation_en", "")
            else:
                print(f"  = {v.polish!r}: already base form, skip")
            unchanged += 1
            continue

        # Does the lemma already exist as a canonical row?
        canonical = db.query(models.Vocabulary).filter(
            models.Vocabulary.id != v.id,
            models.Vocabulary.polish.ilike(lemma),
        ).first()
        if canonical:
            print(f"  ⨉ {v.polish!r} → lemma {lemma!r} already exists (#{canonical.id}) → dedupe, migrate progress")
            if not DRY_RUN:
                migrate_and_delete(db, v, canonical.id)
            deduped += 1
        else:
            print(f"  → {v.polish!r} → {lemma!r} ({res.get('translation_ru')}) — rewrite in place")
            if not DRY_RUN:
                v.polish = lemma
                v.translation_ru = res.get("translation_ru", v.translation_ru)
                v.translation_en = res.get("translation_en", "")
            normalized += 1

    if not DRY_RUN:
        db.commit()
    db.close()
    print(f"\nDone: {normalized} rewritten, {deduped} deduped, {unchanged} already-base.")


if __name__ == "__main__":
    asyncio.run(main())

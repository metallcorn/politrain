from fastapi import APIRouter, Depends
from auth import get_current_user
import models
from services import stt, tts

router = APIRouter(tags=["stt_tts"])


@router.post("/stt/transcribe")
async def transcribe(_: models.User = Depends(get_current_user)):
    return await stt.transcribe(b"")


@router.post("/tts/synthesize")
async def synthesize(body: dict, _: models.User = Depends(get_current_user)):
    return await tts.synthesize(body.get("text", ""), body.get("language", "pl"))

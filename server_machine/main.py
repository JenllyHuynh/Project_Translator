"""
  PROJECT TRANSLATOR - SERVER (Máy Phụ 16GB RAM DDR5)

  Chạy: uvicorn main:app --host 0.0.0.0 --port 8000

  Pipeline mỗi request:
    WAV bytes -> Whisper medium (transcribe, task="transcribe") -> EN text
                                                                          │
                  Whisper medium (translate,  task="translate") -> VI text
                                                                          │
    Response: { "en": "...", "vi": "...", ... }

  Lưu ý:
    - Whisper "translate" dịch THẲNG audio -> tiếng Anh (OpenAI gốc)
    - Mình dùng nó để lấy bản "dịch nghĩa Anh", sau đó chạy
      thêm 1 pass "transcribe vi" để ra tiếng Việt
    - Thực ra faster-whisper không dịch sang tiếng Việt trực tiếp
      -> Giải pháp: transcribe EN + dùng Helsinki-NLP opus-mt hoặc
        chạy 2 model. Cách đơn giản nhất: dùng googletrans (free).
    - Vì "miễn phí, không API", mình dùng googletrans
      (unofficial Google Translate, không cần key, ~200ms/chunk).
"""

import io
import time
import wave
import asyncio
import logging
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
from googletrans import Translator as GTranslator


#  Cấu hình
MODEL_SIZE   = "medium"  # ~769MB, chính xác nhất cho CPU
LANGUAGE     = "en"       # Ngôn ngữ nguồn - Anh
DEVICE       = "cpu"      # AMD iGPU không có CUDA
COMPUTE_TYPE = "int8"     # Nhanh nhất trên CPU, tiết kiệm ~40% RAM


#  Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

#  FastAPI
app = FastAPI(title="Translator Server", version="2.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

#  Load Whisper 1 lần khi khởi động
log.info(f"Loading Whisper '{MODEL_SIZE}' (~769MB, lần đầu sẽ tải về)...")
whisper_model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
log.info("Whisper sẵn sàng!")

# Google Translate client (không cần API key)
gtrans = GTranslator()
log.info("Google Translate client sẵn sàng!")


#  Helper: WAV bytes -> numpy float32
def wav_bytes_to_numpy(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    buf = io.BytesIO(audio_bytes)
    with wave.open(buf, "rb") as wf:
        sr         = wf.getframerate()
        n_frames   = wf.getnframes()
        n_channels = wf.getnchannels()
        sampwidth  = wf.getsampwidth()
        raw        = wf.readframes(n_frames)

    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    dtype     = dtype_map.get(sampwidth, np.int16)
    audio     = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    if n_channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)

    audio /= float(np.iinfo(dtype).max)
    return audio, sr

#  Helper: Dịch EN -> VI bằng googletrans
async def translate_vi(en_text: str) -> tuple[str, int]:
    """
    Dùng googletrans (unofficial, miễn phí, không cần key).
    Chạy trong executor để không block async event loop.
    Trả về (vi_text, elapsed_ms).
    """
    if not en_text.strip():
        return "", 0

    t0 = time.time()
    loop = asyncio.get_event_loop()

    def _do_translate():
        try:
            result = gtrans.translate(en_text, src="en", dest="vi")
            return result.text
        except Exception as e:
            log.warning(f"googletrans lỗi: {e}")
            return ""

    vi_text = await loop.run_in_executor(None, _do_translate)
    elapsed = int((time.time() - t0) * 1000)
    return vi_text, elapsed

#  Endpoints
@app.get("/health")
def health_check():
    return {
        "status":        "ok",
        "whisper_model": MODEL_SIZE,
        "device":        DEVICE,
        "translation":   "googletrans (free, no key)",
    }


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Nhận WAV bytes -> Whisper transcribe EN -> googletrans dịch VI.

    Response:
    {
        "en":           "Hello everyone, let's start",
        "vi":           "Xin chào mọi người, hãy bắt đầu",
        "lang_prob":    0.97,
        "whisper_ms":   1400,
        "translate_ms": 230,
        "total_ms":     1630
    }
    """
    t0 = time.time()

    audio_bytes = await audio.read()
    if len(audio_bytes) < 1000:
        raise HTTPException(400, "Audio quá ngắn hoặc rỗng")

    log.info(f" Nhận {len(audio_bytes)/1024:.1f}KB")

    try:
        audio_np, _ = wav_bytes_to_numpy(audio_bytes)
    except Exception as e:
        raise HTTPException(422, f"Lỗi đọc WAV: {e}")

    # Bước 1: Whisper transcribe tiếng Anh
    t_w = time.time()
    loop = asyncio.get_event_loop()

    segments, info = await loop.run_in_executor(
        None,
        lambda: whisper_model.transcribe(
            audio_np,
            language=LANGUAGE,
            beam_size=4,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250},
            condition_on_previous_text=False,
        ),
    )

    en_text    = " ".join(s.text.strip() for s in segments).strip()
    whisper_ms = int((time.time() - t_w) * 1000)
    log.info(f"🗣  Whisper [{whisper_ms}ms] prob={info.language_probability:.2f}: {en_text[:80]}")

    if not en_text:
        return {"en": "", "vi": "", "lang_prob": 0,
                "whisper_ms": whisper_ms, "translate_ms": 0,
                "total_ms": int((time.time() - t0) * 1000)}

    # Bước 2: Dịch sang tiếng Việt (async, song song được)
    vi_text, translate_ms = await translate_vi(en_text)
    log.info(f"🇻🇳 Dịch [{translate_ms}ms]: {vi_text[:80]}")

    total_ms = int((time.time() - t0) * 1000)
    log.info(f"⏱  Tổng: {total_ms}ms")

    return {
        "en":           en_text,
        "vi":           vi_text,
        "lang_prob":    round(info.language_probability, 3),
        "whisper_ms":   whisper_ms,
        "translate_ms": translate_ms,
        "total_ms":     total_ms,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

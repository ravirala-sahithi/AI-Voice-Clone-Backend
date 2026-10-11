
import os
import tempfile
from contextlib import asynccontextmanager

import librosa
import numpy as np
import torch
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from transformers import AutoFeatureExtractor

# ── Add bundled ffmpeg to PATH so librosa can decode WEBM/OGG/MP4 ──────────
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    if _ffmpeg_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    print(f"ffmpeg found via imageio-ffmpeg: {imageio_ffmpeg.get_ffmpeg_exe()}")
except ImportError:
    print("imageio-ffmpeg not installed — WEBM recording may not decode. Run: pip install imageio-ffmpeg")

# ── Model loader compatible with Transformers 4.x AND 5.x ───────────────────
try:
    from transformers import Wav2Vec2ForSequenceClassification
    _USE_WAV2VEC2_CLASS = True
except ImportError:
    from transformers import AutoModelForAudioClassification
    _USE_WAV2VEC2_CLASS = False

MODEL_NAME = "garystafford/wav2vec2-deepfake-voice-detector"
MAX_FILE_SIZE = 20 * 1024 * 1024
MAX_DURATION_SECONDS = 13

model = None
feature_extractor = None
device = "cuda" if torch.cuda.is_available() else "cpu"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, feature_extractor

    print(f"Loading AI model: {MODEL_NAME}")
    print(f"Using device: {device}")

    feature_extractor = AutoFeatureExtractor.from_pretrained(MODEL_NAME)
    if _USE_WAV2VEC2_CLASS:
        model = Wav2Vec2ForSequenceClassification.from_pretrained(MODEL_NAME)
    else:
        model = AutoModelForAudioClassification.from_pretrained(MODEL_NAME)
    model.to(device)
    model.eval()

    print("AI voice detection model loaded successfully.")
    yield


app = FastAPI(
    title="VoiceGuard AI Detection API",
    description="AI-generated voice detection service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def home():
    return {
        "message": "VoiceGuard AI Detection API",
        "status": "running",
        "model": MODEL_NAME,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "device": device,
    }


@app.post("/detect")
async def detect_voice(file: UploadFile = File(...)):
    if model is None or feature_extractor is None:
        raise HTTPException(
            status_code=503,
            detail="AI model is not ready. Please try again.",
        )

    allowed_extensions = {
        ".wav", ".mp3", ".flac", ".ogg", ".m4a", ".webm", ".mp4"
    }

    filename = file.filename or "audio.wav"
    extension = os.path.splitext(filename)[1].lower()

    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format.",
        )

    content = await file.read(MAX_FILE_SIZE + 1)
    await file.close()

    if not content:
        raise HTTPException(status_code=400, detail="The file is empty.")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Maximum upload size is 20 MB.",
        )

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=extension, delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        # Load audio as mono at the model's expected sample rate.
        audio, sample_rate = librosa.load(
            temp_path,
            sr=16000,
            mono=True,
        )

        if len(audio) == 0:
            raise HTTPException(
                status_code=400,
                detail="No usable audio was found in the file.",
            )

        duration_seconds = len(audio) / sample_rate

        if duration_seconds < 1:
            raise HTTPException(
                status_code=400,
                detail="Please upload at least 1 second of audio.",
            )

        # This model was trained on clips up to about 13 seconds.
        # For longer recordings, analyze the first 13 seconds.
        audio_was_trimmed = duration_seconds > MAX_DURATION_SECONDS

        if audio_was_trimmed:
            audio = audio[: int(MAX_DURATION_SECONDS * sample_rate)]

        inputs = feature_extractor(
            audio,
            sampling_rate=16000,
            return_tensors="pt",
            padding=True,
        )

        inputs = {
            key: value.to(device)
            for key, value in inputs.items()
        }

        with torch.inference_mode():
            outputs = model(**inputs)
            probabilities = torch.softmax(
                outputs.logits, dim=-1
            )[0].cpu().tolist()

        # This model's documented class order is:
        # index 0 = real, index 1 = AI-generated/fake.
        real_probability = float(probabilities[0])
        fake_probability = float(probabilities[1])

        prediction = (
            "AI_GENERATED"
            if fake_probability > 0.5
            else "LIKELY_REAL"
        )

        return {
            "filename": filename,
            "prediction": prediction,
            "real_probability": round(real_probability, 4),
            "ai_generated_probability": round(fake_probability, 4),
            "confidence_percent": round(
                max(real_probability, fake_probability) * 100, 2
            ),
            "analyzed_duration_seconds": round(
                len(audio) / sample_rate, 2
            ),
            "original_duration_seconds": round(
                duration_seconds, 2
            ),
            "audio_was_trimmed": audio_was_trimmed,
            "model": MODEL_NAME,
            "notice": (
                "Experimental prediction, not proof of authenticity."
            ),
        }

    except HTTPException:
        raise

    except Exception as exc:
        print(f"Audio analysis error: {type(exc).__name__}: {exc}")
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not process this audio file. "
                "Try a valid WAV or MP3 recording."
            ),
        ) from exc

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

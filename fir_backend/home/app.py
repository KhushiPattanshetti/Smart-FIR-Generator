import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
import speech_recognition as sr
from pydub import AudioSegment
from deep_translator import GoogleTranslator
import joblib
import warnings
import logging
warnings.filterwarnings("ignore", category=UserWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('flask_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Load ML models
ipc_model = joblib.load("ipc_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

# Ensure uploads directory exists
os.makedirs("uploads", exist_ok=True)

def check_ffmpeg_installed():
    """Check if ffmpeg is installed."""
    if os.system("ffmpeg -version") != 0:
        raise RuntimeError("FFmpeg is not installed or not in PATH.")

def prepare_voice_file(path: str) -> str:
    """Convert various audio formats to WAV."""
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    
    if ext == ".wav":
        return path
    elif ext in (".mp3", ".m4a", ".ogg", ".flac", ".mpeg"):
        audio_file = AudioSegment.from_file(path, format=ext[1:])
        wav_file = os.path.splitext(path)[0] + ".wav"
        audio_file.export(wav_file, format="wav")
        return wav_file
    else:
        raise ValueError(f"Unsupported audio format: {ext}")

def transcribe_audio(audio_path, language="en-US"):
    """Transcribe audio to text."""
    r = sr.Recognizer()
    with sr.AudioFile(audio_path) as source:
        audio_data = r.record(source)
        try:
            text = r.recognize_google(audio_data, language=language)
            return text
        except sr.UnknownValueError:
            return "Could not understand the audio."
        except sr.RequestError:
            return "Google API request failed."

def translate_to_english(text):
    """Translate text to English."""
    if not text or text.strip() == "":
        return ""
    return GoogleTranslator(source="auto", target="en").translate(text)

def predict_ipc_section(text):
    """Predict IPC section using ML model."""
    if not text or text.strip() == "":
        return "Unknown"
    text_vectorized = vectorizer.transform([text])
    return ipc_model.predict(text_vectorized)[0]

@app.route("/upload", methods=["POST"])
def upload_audio():
    """Handle audio file upload and processing."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    language = request.form.get("language", "en-US")

    if file.filename == "":
        return jsonify({"error": "Empty file"}), 400

    file_path = f"uploads/{uuid.uuid4().hex}_{file.filename}"
    file.save(file_path)

    try:
        check_ffmpeg_installed()
        wav_file = prepare_voice_file(file_path)
        text = transcribe_audio(wav_file, language)
        translated_text = translate_to_english(text)
        ipc_section = predict_ipc_section(translated_text)

        # Clean up temporary files
        os.remove(file_path)
        if wav_file != file_path:
            os.remove(wav_file)

        return jsonify({
            "original_text": text,
            "translated_text": translated_text,
            "ipc_section": ipc_section,
            "confidence_score": 0.85  # Placeholder - replace with actual confidence if available
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/predict", methods=["POST"])
def predict_from_text():
    """Handle text input for IPC prediction with better error handling"""
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    try:
        data = request.get_json()
        if not data or 'text' not in data or not data['text'].strip():
            return jsonify({"error": "No valid text provided"}), 400

        text = data['text'].strip()
        
        # Translation
        translated_text = ""
        try:
            if text:
                translated_text = GoogleTranslator(source="auto", target="en").translate(text)
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            translated_text = f"[Translation failed: {str(e)}] Original: {text}"

        # IPC Prediction
        ipc_section = "Unknown"
        try:
            if translated_text:
                text_vectorized = vectorizer.transform([translated_text])
                ipc_section = ipc_model.predict(text_vectorized)[0]
        except Exception as e:
            logger.error(f"Prediction error: {str(e)}")
            ipc_section = "Prediction failed"

        return jsonify({
            "original_text": text,
            "translated_text": translated_text,
            "ipc_section": ipc_section,
            "confidence_score": 0.85,
            "status": "success"
        })

    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
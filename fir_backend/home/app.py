import os
import uuid
from flask import Flask, request, jsonify
from flask_cors import CORS
import speech_recognition as sr
from pydub import AudioSegment
from deep_translator import GoogleTranslator
import joblib  # For loading ML model
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

ipc_model = joblib.load("ipc_model.pkl")
vectorizer = joblib.load("vectorizer.pkl")

def check_ffmpeg_installed():
    """Checks if ffmpeg is installed."""
    if os.system("ffmpeg -version") != 0:
        raise RuntimeError("FFmpeg is not installed or not in PATH.")

def prepare_voice_file(path: str) -> str:
    """Converts various audio formats to WAV."""
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
    """Transcribes audio to text."""
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
    """Translates text to English."""
    return GoogleTranslator(source="auto", target="en").translate(text)

def predict_ipc_section(text):
    """Predicts IPC section using a trained ML model."""
    text_vectorized = vectorizer.transform([text])
    predicted_section = ipc_model.predict(text_vectorized)[0]
    return predicted_section

@app.route("/upload", methods=["POST"])
def upload_audio():
    """Handles file upload, transcription, translation, and IPC prediction."""
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

        # Clean up
        os.remove(file_path)
        if wav_file != file_path:
            os.remove(wav_file)

        return jsonify({
            "original_text": text,
            "translated_text": translated_text,
            "ipc_section": ipc_section
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(host="0.0.0.0", port=5001, debug=True)
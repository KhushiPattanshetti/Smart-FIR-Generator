import os
import speech_recognition as sr
from pydub import AudioSegment
from deep_translator import GoogleTranslator

def check_ffmpeg_installed():
    """Checks if ffmpeg is installed and accessible."""
    if os.system("ffmpeg -version") != 0:
        raise RuntimeError("FFmpeg is not installed or not in PATH. Install it from https://ffmpeg.org/download.html")

def prepare_voice_file(path: str) -> str:
    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext == '.wav':
        return path
    elif ext in ('.mp3', '.m4a', '.ogg', '.flac', '.mpeg'):
        try:
            audio_file = AudioSegment.from_file(path, format=ext[1:])
            wav_file = os.path.splitext(path)[0] + '.wav'
            audio_file.export(wav_file, format='wav')
            return wav_file
        except Exception as e:
            raise RuntimeError(f"Error converting {path} to WAV: {e}")
    else:
        raise ValueError(f'Unsupported audio format: {ext}')

def transcribe_audio(audio_data, language) -> str:
    """
    Transcribes audio data to text using Google's speech recognition API.
    """
    r = sr.Recognizer()
    try:
        text = r.recognize_google(audio_data, language=language)
        return text
    except sr.UnknownValueError:
        return "Google Speech Recognition could not understand the audio."
    except sr.RequestError:
        return "Could not request results from Google Speech Recognition service."

def translate_to_english(text: str) -> str:
    """
    Translates the given text to English using Deep Translator.
    """
    try:
        translated_text = GoogleTranslator(source='auto', target='en').translate(text)
        return translated_text
    except Exception as e:
        return f"Translation error: {e}"

def write_transcription_to_file(text, output_file) -> None:
    """
    Writes the transcribed and translated text to the output file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception as e:
        raise RuntimeError(f"Error writing transcription to file: {e}")

def speech_to_text(input_path: str, output_path: str, language: str) -> None:
    """
    Transcribes an audio file at the given path to text, translates it to English, 
    and writes both original and translated text to the output file.
    """
    check_ffmpeg_installed()

    wav_file = prepare_voice_file(input_path)

    try:
        with sr.AudioFile(wav_file) as source:
            audio_data = sr.Recognizer().record(source)
            original_text = transcribe_audio(audio_data, language)
            translated_text = translate_to_english(original_text)

            # Combine both transcriptions
            final_output = f"Original Text ({language}):\n{original_text}\n\nTranslated to English:\n{translated_text}"

            write_transcription_to_file(final_output, output_path)
            print("Transcription and Translation:\n", final_output)
    finally:
        if wav_file != input_path:  # Remove temp WAV file if it was created
            os.remove(wav_file)

if __name__ == '__main__':
    print('Please enter the path to an audio file (WAV, MP3, M4A, OGG, FLAC, MPEG):')
    input_path = input().strip()

    if not os.path.isfile(input_path):
        print('Error: File not found.')
        exit(1)

    print('Please enter the path to the output file (including .txt extension):')
    output_path = input().strip()

    if not output_path.endswith(".txt"):
        print('Error: Output file must be a .txt file.')
        exit(1)

    print('Please enter the language code (e.g., en-US, es, fr, de, hi, zh-CN):')
    language = input().strip()

    try:
        speech_to_text(input_path, output_path, language)
    except Exception as e:
        print('Error:', e)
        exit(1)

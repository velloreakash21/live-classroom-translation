"""Configuration for Live Classroom Translation app."""

# Audio constants
SAMPLE_RATE = 48000
CHANNELS = 1
BUFFER_DURATION = 3  # seconds
SILENCE_THRESHOLD = 500  # energy threshold for VAD
FRAME_SIZE = 960  # samples per frame (20ms at 48kHz)

# Groq models
STT_MODEL = "whisper-large-v3-turbo"
TRANSLATION_MODEL = "llama-3.3-70b-versatile"

# Language configuration with edge-tts voice mappings
LANGUAGE_CONFIG = {
    "Hindi": {
        "code": "hi",
        "male_voice": "hi-IN-MadhurNeural",
        "female_voice": "hi-IN-SwaraNeural",
    },
    "Bengali": {
        "code": "bn",
        "male_voice": "bn-IN-BashkarNeural",
        "female_voice": "bn-IN-TanishaaNeural",
    },
    "Gujarati": {
        "code": "gu",
        "male_voice": "gu-IN-NiranjanNeural",
        "female_voice": "gu-IN-DhwaniNeural",
    },
    "Kannada": {
        "code": "kn",
        "male_voice": "kn-IN-GaganNeural",
        "female_voice": "kn-IN-SapnaNeural",
    },
    "Malayalam": {
        "code": "ml",
        "male_voice": "ml-IN-MidhunNeural",
        "female_voice": "ml-IN-SobhanaNeural",
    },
    "Marathi": {
        "code": "mr",
        "male_voice": "mr-IN-ManoharNeural",
        "female_voice": "mr-IN-AarohiNeural",
    },
    "Tamil": {
        "code": "ta",
        "male_voice": "ta-IN-ValluvarNeural",
        "female_voice": "ta-IN-PallaviNeural",
    },
    "Telugu": {
        "code": "te",
        "male_voice": "te-IN-MohanNeural",
        "female_voice": "te-IN-ShrutiNeural",
    },
    "Urdu": {
        "code": "ur",
        "male_voice": "ur-IN-SalmanNeural",
        "female_voice": "ur-IN-GulNeural",
    },
}

# Live Classroom Translation

Real-time English to Indian language translation for classrooms. A teacher speaks English into a microphone, and students hear the translated audio in their selected language through headphones — all in under 5 seconds.

**[Try the live demo](https://live-classroom-translation-india.streamlit.app/)**

## How It Works

```
Browser Mic → WebRTC (stereo s16 48kHz)
                  ↓
         Audio buffering (3s, energy-based VAD)
                  ↓
         Groq Whisper STT → English text
                  ↓
         Groq Llama 3.3 → Translated text
                  ↓
         edge-tts Neural Voice → Audio
                  ↓
         WebRTC → Student's headphones
```

## Supported Languages

| Language   | Male Voice              | Female Voice            |
|------------|-------------------------|-------------------------|
| Hindi      | hi-IN-MadhurNeural      | hi-IN-SwaraNeural       |
| Bengali    | bn-IN-BashkarNeural     | bn-IN-TanishaaNeural    |
| Gujarati   | gu-IN-NiranjanNeural    | gu-IN-DhwaniNeural      |
| Kannada    | kn-IN-GaganNeural       | kn-IN-SapnaNeural       |
| Malayalam  | ml-IN-MidhunNeural      | ml-IN-SobhanaNeural     |
| Marathi    | mr-IN-ManoharNeural     | mr-IN-AarohiNeural      |
| Tamil      | ta-IN-ValluvarNeural    | ta-IN-PallaviNeural     |
| Telugu     | te-IN-MohanNeural       | te-IN-ShrutiNeural      |
| Urdu       | ur-IN-SalmanNeural      | ur-IN-GulNeural         |

## Tech Stack

| Component        | Technology                              |
|------------------|-----------------------------------------|
| Frontend         | Streamlit                               |
| Real-time Audio  | streamlit-webrtc (aiortc)               |
| Speech-to-Text   | Groq Whisper (`whisper-large-v3-turbo`) |
| Translation      | Groq Llama 3.3 (`llama-3.3-70b-versatile`) |
| Text-to-Speech   | edge-tts (Microsoft Neural Voices)      |
| Audio Processing | PyAV + pydub + numpy                    |

## Quick Start

### Prerequisites

- Python 3.10+
- [Groq API key](https://console.groq.com/keys) (free tier available)
- ffmpeg (`brew install ffmpeg` on macOS, `apt install ffmpeg` on Linux)

### Setup

```bash
# Clone the repo
git clone https://github.com/velloreakash21/live-classroom-translation.git
cd live-classroom-translation

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set your Groq API key
echo "GROQ_API_KEY=gsk_your_key_here" > .env

# Run the app
streamlit run app.py
```

Open http://localhost:8501, select a language, click **START**, and speak English.

> **Use headphones** to avoid feedback loops between speaker and microphone.

## Project Structure

```
├── app.py                    # Streamlit UI + WebRTC wiring
├── audio_processor.py        # TranslationProcessor (threading, queues, VAD)
├── translation_pipeline.py   # Groq STT → Groq LLM → edge-tts
├── config.py                 # Voice mappings, audio constants, model IDs
├── utils.py                  # PCM↔WAV, MP3→PCM frame converters
├── requirements.txt          # Python dependencies
├── packages.txt              # System dependencies for Streamlit Cloud
├── .env.example              # Environment variable template
└── REPORT.md                 # Detailed technical report with latency & cost
```

## Performance

Measured pipeline latency (Hindi, Feb 2026):

| Stage      | Avg Time |
|------------|----------|
| STT        | ~0.45s   |
| Translation| ~0.30s   |
| TTS        | ~1.10s   |
| **Total**  | **~1.95s** |

End-to-end (including 3s buffer): ~5 seconds from speech to translated audio.

## Cost

| Duration       | Cost    |
|----------------|---------|
| 1 hour         | $0.10   |
| 8-hour day     | $0.81   |
| 30-day month   | $24.24  |

> A full classroom day of continuous live translation costs under $1.

See [REPORT.md](REPORT.md) for detailed cost breakdown.

## Deployment

The app is deployed on [Streamlit Community Cloud](https://streamlit.io/cloud). To deploy your own:

1. Fork this repository
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo and select `app.py`
4. Add `GROQ_API_KEY` in the app's Secrets settings
5. Deploy

## License

MIT

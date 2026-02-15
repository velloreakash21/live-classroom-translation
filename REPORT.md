# Live Classroom Translation POC — Technical Report

## Architecture

```
Browser Mic → WebRTC (stereo s16 48kHz)
                  ↓
         audio_frame_callback (~50x/sec, <1ms)
                  ↓
         PCM buffer (3s, mono, energy-based VAD)
                  ↓
         ┌─── Background Thread ───────────────────┐
         │  Groq Whisper STT (whisper-large-v3-turbo) │
         │           ↓                              │
         │  Groq LLM Translation (llama-3.3-70b)   │
         │           ↓                              │
         │  edge-tts Neural Voice (MP3 synthesis)   │
         └──────────────────────────────────────────┘
                  ↓
         PCM frames → output_queue → WebRTC → Headphones
```

## Tech Stack

| Component          | Technology                        | Version     |
|--------------------|-----------------------------------|-------------|
| Frontend           | Streamlit                         | 1.54.0      |
| Real-time Audio    | streamlit-webrtc (aiortc)         | 0.64.5      |
| Speech-to-Text     | Groq Whisper (`whisper-large-v3-turbo`) | API   |
| Translation LLM    | Groq Llama 3.3 (`llama-3.3-70b-versatile`) | API |
| Text-to-Speech     | edge-tts (Microsoft Neural Voices)| 7.2.7       |
| Audio Processing   | PyAV + pydub + numpy              | —           |
| Runtime            | Python                            | 3.14.2      |

### Supported Languages & Voices

| Language   | Male Voice              | Female Voice            |
|------------|-------------------------|-------------------------|
| Hindi      | hi-IN-MadhurNeural      | hi-IN-SwaraNeural       |
| Telugu     | te-IN-MohanNeural       | te-IN-ShrutiNeural      |
| Tamil      | ta-IN-ValluvarNeural    | ta-IN-PallaviNeural     |
| Malayalam  | ml-IN-MidhunNeural      | ml-IN-SobhanaNeural     |

## Measured Latency

Tested on Feb 15, 2026. Target language: Hindi.

| Utterance                       | STT    | Translate | TTS    | Total Pipeline |
|---------------------------------|--------|-----------|--------|----------------|
| "Hi, how are you?"              | 0.43s  | 0.21s     | 0.91s  | **1.65s**      |
| "Is it good?"                   | 0.47s  | 0.19s     | 1.21s  | **1.93s**      |
| "Let me see if it is working."  | 0.46s  | 0.54s     | 1.18s  | **2.26s**      |

### Latency Summary

| Metric                    | Value       |
|---------------------------|-------------|
| Average pipeline latency  | **1.95s**   |
| Buffer wait time          | **3.00s**   |
| End-to-end (speech → audio) | **~5.0s** |
| Target                    | < 4.0s pipeline |

**Bottleneck:** TTS (edge-tts) accounts for ~55% of pipeline time (~1.1s avg).

## Cost Analysis

### Per-API Pricing (Groq, as of Feb 2026)

| Service                           | Unit Price                          |
|-----------------------------------|-------------------------------------|
| Groq Whisper (`whisper-large-v3-turbo`) | $0.04 / hour of audio          |
| Groq LLM (`llama-3.3-70b-versatile`) — Input | $0.59 / 1M tokens          |
| Groq LLM (`llama-3.3-70b-versatile`) — Output | $0.79 / 1M tokens         |
| edge-tts (Microsoft Neural Voices) | **Free**                           |

### Usage Model (Continuous Speech)

Assumptions:
- 3-second buffer → **20 chunks per minute** of continuous speech
- Per chunk: ~60 input tokens (system prompt + English text), ~20 output tokens (translated text)

| Component     | Per Minute Usage           | Cost / Minute | Cost / Hour |
|---------------|----------------------------|---------------|-------------|
| **STT**       | 1 min of audio             | $0.00067      | $0.040      |
| **LLM Input** | 20 × 60 = 1,200 tokens    | $0.00071      | $0.042      |
| **LLM Output**| 20 × 20 = 400 tokens      | $0.00032      | $0.019      |
| **TTS**       | —                          | $0.00000      | $0.000      |
| **Total**     |                            | **$0.00170**  | **$0.101**  |

### Cost Summary

| Duration        | Estimated Cost |
|-----------------|----------------|
| **1 minute**    | $0.002         |
| **1 hour**      | $0.10          |
| **8-hour day**  | $0.81          |
| **30-day month** (8h/day) | $24.24  |

> A full classroom day (8 hours) of continuous live translation costs under $1.

## File Structure

```
tranalation/
├── .env                      # GROQ_API_KEY
├── .gitignore
├── requirements.txt          # 8 dependencies
├── packages.txt              # System deps for Streamlit Cloud (ffmpeg)
├── config.py                 # Voice mappings, audio constants, model IDs
├── utils.py                  # PCM↔WAV, MP3→PCM frame converters
├── translation_pipeline.py   # Groq STT → Groq LLM → edge-tts
├── audio_processor.py        # TranslationProcessor (threading, queues, VAD)
└── app.py                    # Streamlit UI + WebRTC wiring
```

## How to Run

```bash
# Set your Groq API key
echo "GROQ_API_KEY=gsk_..." > .env

# Create venv and install
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Launch
streamlit run app.py
```

Open http://localhost:8501, select language, click START, and speak English.
**Use headphones** to avoid echo loop.

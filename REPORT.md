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
| Bengali    | bn-IN-BashkarNeural     | bn-IN-TanishaaNeural    |
| Gujarati   | gu-IN-NiranjanNeural    | gu-IN-DhwaniNeural      |
| Kannada    | kn-IN-GaganNeural       | kn-IN-SapnaNeural       |
| Malayalam  | ml-IN-MidhunNeural      | ml-IN-SobhanaNeural     |
| Marathi    | mr-IN-ManoharNeural     | mr-IN-AarohiNeural      |
| Tamil      | ta-IN-ValluvarNeural    | ta-IN-PallaviNeural     |
| Telugu     | te-IN-MohanNeural       | te-IN-ShrutiNeural      |
| Urdu       | ur-IN-SalmanNeural      | ur-IN-GulNeural         |

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

## Latency Optimization Roadmap

### Current Bottleneck Breakdown

```
Buffer wait:  ████████████████████████  3.00s  (60%)
STT:          ███                       0.45s  (9%)
Translation:  ██                        0.30s  (6%)
TTS:          ███████                   1.10s  (22%)
Overhead:     █                         0.15s  (3%)
              ─────────────────────────────────
Total:                                  ~5.00s
```

The 3-second audio buffer is the single largest contributor to end-to-end latency. The current architecture is **batch-oriented** — it collects a fixed window of audio, then processes it sequentially. A streaming architecture can eliminate the buffer entirely and overlap pipeline stages.

### Optimization 1: Streaming STT (eliminates 3s buffer)

Replace the batch STT (buffer → Whisper API call) with a **streaming STT** service that receives audio continuously via WebSocket and returns partial transcripts in real-time.

| Service | Latency (first word) | Cost | Notes |
|---------|---------------------|------|-------|
| **Deepgram Nova-2** | ~300ms | $0.0059/min | Best price-to-performance; English streaming; built-in VAD |
| **Azure Speech Services** | ~200ms | $1.00/hr | Excellent Indian language support; WebSocket streaming |
| **Google Cloud STT v2** | ~300ms | $0.024/min | Wide language support; streaming gRPC API |
| **AssemblyAI Real-time** | ~300ms | $0.0065/min | Simple WebSocket API; English-focused |

**Estimated impact:** 3.0s → ~0.3s buffer+STT (saves ~2.7s).

**Recommended pick:** Deepgram Nova-2 — cheapest, fastest, built-in endpointing/VAD, simple WebSocket API.

### Optimization 2: Streaming TTS (reduces ~1.1s to ~0.2s)

edge-tts synthesizes the entire MP3 file before returning it. **Streaming TTS** services send audio chunks as they are generated, so playback can begin before synthesis completes.

| Service | First-byte Latency | Quality | Cost | Indian Language Support |
|---------|-------------------|---------|------|------------------------|
| **Cartesia Sonic** | ~90ms | Very good | $0.042/1K chars | Limited |
| **ElevenLabs Turbo v2.5** | ~300ms | Excellent | $0.30/1K chars | Hindi, Telugu, Tamil + more |
| **Azure Neural TTS** (WebSocket) | ~200ms | Great | $16/1M chars (~$0.016/1K) | All 9 Indian languages |
| **Deepgram Aura** | ~250ms | Good | $0.0150/1K chars | Limited |
| **PlayHT** (streaming) | ~300ms | Great | $0.05/1K chars | Some Indian languages |
| **edge-tts** (current) | ~1100ms | Good | **Free** | All 9 Indian languages |

**Estimated impact:** 1.1s → ~0.2-0.3s (saves ~0.8s).

**Recommended pick:** Azure Neural TTS via WebSocket — supports all 9 Indian languages already configured, sub-200ms first byte, affordable at ~$0.016 per 1K characters.

### Optimization 3: Faster / Streaming Translation

| Approach | Latency | Cost |
|----------|---------|------|
| **Groq Llama 3.3** (current, batch) | ~300ms | $0.59/$0.79 per 1M tokens |
| **Groq Llama 3.3** (streaming tokens) | ~100ms first token | Same |
| **Cerebras Inference** | ~50ms first token | Similar |
| **Google Translate API** | ~100-200ms | $20/1M chars |
| **DeepL API** | ~100-200ms | $25/1M chars |

Streaming the LLM response allows the TTS stage to begin as soon as the first sentence boundary is detected, rather than waiting for the full translation.

**Estimated impact:** 0.3s → ~0.1s (saves ~0.2s).

### Projected Latency by Upgrade Tier

| Configuration | Buffer | STT | Translate | TTS | Total E2E | Est. Cost/hr |
|---------------|--------|-----|-----------|-----|-----------|-------------|
| **Current (POC)** | 3.0s | 0.45s | 0.30s | 1.10s | **~5.0s** | $0.10 |
| **Tier 1:** Streaming STT | 0s | 0.30s | 0.30s | 1.10s | **~1.7s** | $0.15 |
| **Tier 2:** + Streaming TTS | 0s | 0.30s | 0.30s | 0.25s | **~0.85s** | $0.50 |
| **Tier 3:** Full streaming pipeline | 0s | 0.20s | 0.10s | 0.20s | **~0.5s** | $1–2 |

### Architecture Change: Batch → Streaming

The current POC uses a batch architecture where each stage completes before the next begins:

```
Current (batch):
  [====3s buffer====] → [STT] → [Translate] → [TTS] → [Play]
                         0.45s    0.30s         1.10s
```

A streaming architecture overlaps all stages and eliminates the buffer:

```
Streaming (pipelined):
  audio──→ STT words──→ translate sentence──→ TTS chunks──→ play
  audio──→ STT words──→ translate sentence──→ TTS chunks──→ play
  (continuous, overlapping — each stage feeds the next in real-time)
```

Key implementation changes required:
1. **WebSocket connections** to STT and TTS services (persistent, not per-request)
2. **Sentence boundary detection** between STT and translation to trigger translation at natural pause points
3. **Async pipeline** replacing the current threading model — all stages run concurrently with async generators
4. **Chunk-level TTS playback** — begin playing audio as soon as the first TTS chunk arrives, not after full synthesis

### Recommended Upgrade Path

**Phase 1 — Quick win (~1.7s, minimal code change):**
- Replace Groq Whisper batch calls with **Deepgram Nova-2 streaming** WebSocket
- Remove the 3s PCM buffer; let Deepgram handle endpointing/VAD
- Keep Groq translation and edge-tts unchanged
- Cost increase: ~$0.05/hr

**Phase 2 — Sub-second (~0.85s, moderate rewrite):**
- Add **Azure Neural TTS** via WebSocket (streaming playback)
- Enable **Groq streaming** response for translation
- Begin TTS synthesis as soon as first translated sentence is available
- Cost increase: ~$0.40/hr

**Phase 3 — Near real-time (~0.5s, full rewrite):**
- All services connected via persistent WebSockets
- **Deepgram** streaming STT + **Cerebras** streaming translation + **Cartesia Sonic** streaming TTS
- Fully async pipeline with overlapping stages
- Cost: ~$1–2/hr (still under $16/day for 8 hours)

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

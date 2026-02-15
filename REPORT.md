# Live Classroom Translation POC — Technical Report

**Live Demo:** [live-classroom-translation-india.streamlit.app](https://live-classroom-translation-india.streamlit.app/)
**Repository:** [github.com/velloreakash21/live-classroom-translation](https://github.com/velloreakash21/live-classroom-translation)

---

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

### Threading Model

- `recv()` runs on the WebRTC media thread ~50x/sec. Returns in <1ms. Never blocks, never makes API calls.
- A single **background daemon thread** runs the slow pipeline (STT → Translate → TTS).
- Two `queue.Queue` instances decouple the fast callback from slow API calls:
  - `processing_queue` (maxsize=3): audio chunks waiting for pipeline processing
  - `output_queue` (maxsize=500): translated PCM frames waiting for playback

### Audio Format Flow

```
Mic → av.AudioFrame (s16, stereo, 48kHz)
  → stereo-to-mono conversion (average L+R channels)
  → numpy int16 buffer (3s at 48kHz = 144,000 samples)
  → WAV bytes (for Groq Whisper API)
  → English text
  → Translated text (Groq Llama 3.3)
  → MP3 bytes (edge-tts)
  → pydub decode → resample to 48kHz mono s16
  → chunk into 960-sample frames (20ms each)
  → mono-to-stereo duplication (match input layout)
  → av.AudioFrame with pts timestamps
  → WebRTC output → Headphones
```

---

## Tech Stack

| Component          | Technology                              | Version     |
|--------------------|-----------------------------------------|-------------|
| Frontend           | Streamlit                               | 1.54.0      |
| Real-time Audio    | streamlit-webrtc (aiortc)               | 0.64.5      |
| Speech-to-Text     | Groq Whisper (`whisper-large-v3-turbo`) | API         |
| Translation LLM    | Groq Llama 3.3 (`llama-3.3-70b-versatile`) | API     |
| Text-to-Speech     | edge-tts (Microsoft Neural Voices)      | 7.2.7       |
| Audio Processing   | PyAV + pydub + audioop-lts + numpy      | —           |
| Deployment         | Streamlit Community Cloud               | Python 3.13 |
| Runtime (local)    | Python                                  | 3.14.2      |

---

## Supported Languages (9 Indian Languages)

All languages support both male and female neural voices via Microsoft edge-tts.

| Language    | Code | Male Voice              | Female Voice            |
|-------------|------|-------------------------|-------------------------|
| Hindi       | hi   | hi-IN-MadhurNeural      | hi-IN-SwaraNeural       |
| Bengali     | bn   | bn-IN-BashkarNeural     | bn-IN-TanishaaNeural    |
| Gujarati    | gu   | gu-IN-NiranjanNeural    | gu-IN-DhwaniNeural      |
| Kannada     | kn   | kn-IN-GaganNeural       | kn-IN-SapnaNeural       |
| Malayalam   | ml   | ml-IN-MidhunNeural      | ml-IN-SobhanaNeural     |
| Marathi     | mr   | mr-IN-ManoharNeural     | mr-IN-AarohiNeural      |
| Tamil       | ta   | ta-IN-ValluvarNeural    | ta-IN-PallaviNeural     |
| Telugu      | te   | te-IN-MohanNeural       | te-IN-ShrutiNeural      |
| Urdu        | ur   | ur-IN-SalmanNeural      | ur-IN-GulNeural         |

**Input language:** English only (teacher speaks English).

---

## Measured Latency

### Local Testing (Feb 15, 2026, Hindi)

| Utterance                       | STT    | Translate | TTS    | Total Pipeline |
|---------------------------------|--------|-----------|--------|----------------|
| "Hi, how are you?"              | 0.43s  | 0.21s     | 0.91s  | **1.65s**      |
| "Is it good?"                   | 0.47s  | 0.19s     | 1.21s  | **1.93s**      |
| "Let me see if it is working."  | 0.46s  | 0.54s     | 1.18s  | **2.26s**      |

### Streamlit Cloud Testing (Feb 15, 2026, Hindi)

| Utterance                                 | STT    | Translate | TTS    | Total Pipeline |
|-------------------------------------------|--------|-----------|--------|----------------|
| "Hi, how are you? Is it all good?"        | 0.64s  | 0.33s     | 2.06s  | **3.34s**      |
| "Hello."                                  | 0.32s  | 0.32s     | 0.82s  | **1.73s**      |
| "Thank you."                              | 0.36s  | 0.23s     | 0.83s  | **1.81s**      |

### Streamlit Cloud Testing (Feb 15, 2026, Kannada)

| Utterance                                 | STT    | Translate | TTS    | Total Pipeline |
|-------------------------------------------|--------|-----------|--------|----------------|
| "Hi, how are you? Is it fine, everything?"| 0.33s  | 0.50s     | 1.00s  | **2.13s**      |
| "Okay, I just wanted to see"              | 0.33s  | 0.46s     | 1.50s  | **2.62s**      |
| "this thing is working or not. I can"     | 0.39s  | 0.42s     | 0.96s  | **2.15s**      |
| "Thank you."                              | 0.41s  | 0.30s     | 0.97s  | **2.20s**      |

### Latency Summary

| Metric                            | Local   | Cloud (Hindi) | Cloud (Kannada) |
|-----------------------------------|---------|---------------|-----------------|
| Average pipeline latency          | 1.95s   | 2.29s         | 2.28s           |
| Buffer wait time                  | 3.00s   | 3.00s         | 3.00s           |
| End-to-end (speech → audio)       | ~5.0s   | ~5.3s         | ~5.3s           |

**Bottleneck:** TTS (edge-tts) accounts for ~50-55% of pipeline time.

---

## Cost Analysis

### Per-API Pricing (Groq, as of Feb 2026)

| Service                                        | Unit Price               |
|------------------------------------------------|--------------------------|
| Groq Whisper (`whisper-large-v3-turbo`)        | $0.04 / hour of audio    |
| Groq LLM (`llama-3.3-70b-versatile`) — Input  | $0.59 / 1M tokens        |
| Groq LLM (`llama-3.3-70b-versatile`) — Output | $0.79 / 1M tokens        |
| edge-tts (Microsoft Neural Voices)             | **Free**                 |

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

| Duration                  | Estimated Cost |
|---------------------------|----------------|
| **1 minute**              | $0.002         |
| **1 hour**                | $0.10          |
| **8-hour day**            | $0.81          |
| **30-day month** (8h/day) | $24.24        |

> A full classroom day (8 hours) of continuous live translation costs under $1.

---

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

### Latency & Cost Comparison Across Tiers

#### Overview

| Configuration | End-to-End Latency | Latency Reduction | Cost / Hour | Cost / 8hr Day | Cost / Month (8h/day) |
|---------------|-------------------|-------------------|-------------|----------------|----------------------|
| **Current (POC)** | **~5.0s** | — | $0.10 | $0.81 | $24.24 |
| **Tier 1:** Streaming STT | **~1.7s** | 66% faster | $0.15 | $1.20 | $36.00 |
| **Tier 2:** + Streaming TTS | **~0.85s** | 83% faster | $0.50 | $4.00 | $120.00 |
| **Tier 3:** Full streaming | **~0.5s** | 90% faster | $1.50 | $12.00 | $360.00 |

#### Per-Stage Latency Breakdown

| Stage | Current | Tier 1 | Tier 2 | Tier 3 |
|-------|---------|--------|--------|--------|
| Buffer wait | 3.00s | 0s | 0s | 0s |
| STT | 0.45s | 0.30s | 0.30s | 0.20s |
| Translation | 0.30s | 0.30s | 0.15s | 0.10s |
| TTS | 1.10s | 1.10s | 0.25s | 0.20s |
| Overhead | 0.15s | 0s | 0.15s | 0s |
| **Total** | **~5.0s** | **~1.7s** | **~0.85s** | **~0.5s** |

#### Tier 1 — Detailed Cost Breakdown ($0.15/hr)

Replace batch Groq Whisper with streaming Deepgram Nova-2. Eliminates the 3s buffer.

| Component | Service | Cost / Hour |
|-----------|---------|-------------|
| STT | Deepgram Nova-2 (streaming) | $0.035 |
| Translation | Groq Llama 3.3 (batch) | $0.061 |
| TTS | edge-tts (free) | $0.000 |
| **Total** | | **$0.096 → ~$0.15** |

*What changes:* Replace `transcribe()` with Deepgram WebSocket; remove PCM buffer; let Deepgram handle VAD/endpointing.
*Effort:* Minimal — swap one API, remove buffer logic.

#### Tier 2 — Detailed Cost Breakdown ($0.50/hr)

Add Azure Neural TTS streaming and Groq streaming translation.

| Component | Service | Cost / Hour |
|-----------|---------|-------------|
| STT | Deepgram Nova-2 (streaming) | $0.035 |
| Translation | Groq Llama 3.3 (streaming tokens) | $0.061 |
| TTS | Azure Neural TTS (WebSocket) | $0.384 |
| **Total** | | **~$0.50** |

*TTS cost calculation:* ~150 words/min spoken → ~600 chars/min translated → 36,000 chars/hr × $16/1M chars = $0.384/hr.
*What changes:* Add Azure TTS WebSocket connection; stream Groq response tokens; begin TTS as first sentence completes.
*Effort:* Moderate — new TTS integration, async pipeline restructuring.

#### Tier 3 — Detailed Cost Breakdown ($1.50/hr)

All services streaming via persistent WebSockets. Overlapping pipeline stages.

| Component | Service | Cost / Hour |
|-----------|---------|-------------|
| STT | Deepgram Nova-2 (streaming) | $0.035 |
| Translation | Cerebras Inference (streaming) | $0.065 |
| TTS | Cartesia Sonic (streaming) | $1.400 |
| **Total** | | **~$1.50** |

*TTS cost calculation:* ~36,000 chars/hr × $0.042/1K chars = $1.40/hr (Cartesia is premium but ultra-low latency at ~90ms).
*Alternative:* ElevenLabs Turbo at $0.30/1K chars = $10.80/hr (higher quality but significantly more expensive).
*What changes:* Full async WebSocket pipeline; all stages run concurrently; sentence boundary detection between STT and translation.
*Effort:* Full rewrite — new architecture, all new service integrations.

#### Cost vs. Latency Trade-off

```
Cost/hr:  $0.10 ──── $0.15 ──────────── $0.50 ──────────── $1.50
             │          │                   │                   │
Latency:   5.0s ──── 1.7s ──────────── 0.85s ──────────── 0.5s
             │          │                   │                   │
            POC      Tier 1             Tier 2             Tier 3
           (free     (streaming         (streaming         (full
            TTS)      STT only)          STT+TTS)          streaming)
```

> **Best value:** Tier 1 delivers a 66% latency reduction (5.0s → 1.7s) for only $0.05/hr more — practically free at $1.20/day.
> **Best experience:** Tier 2 achieves sub-second latency at $4/day — suitable for production classroom use.

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

**Phase 1 — Quick win (5.0s → 1.7s, +$0.05/hr):**
- Replace Groq Whisper batch calls with **Deepgram Nova-2 streaming** WebSocket
- Remove the 3s PCM buffer; let Deepgram handle endpointing/VAD
- Keep Groq translation and edge-tts unchanged

**Phase 2 — Sub-second (1.7s → 0.85s, +$0.35/hr):**
- Add **Azure Neural TTS** via WebSocket (streaming playback)
- Enable **Groq streaming** response for translation
- Begin TTS synthesis as soon as first translated sentence is available

**Phase 3 — Near real-time (0.85s → 0.5s, +$1.00/hr):**
- All services connected via persistent WebSockets
- **Deepgram** streaming STT + **Cerebras** streaming translation + **Cartesia Sonic** streaming TTS
- Fully async pipeline with overlapping stages

---

## Deployment

### Platform

Deployed on **Streamlit Community Cloud** at [live-classroom-translation-india.streamlit.app](https://live-classroom-translation-india.streamlit.app/).

### Deployment Configuration

- `packages.txt` — System dependency: `ffmpeg` (installed via apt-get)
- `requirements.txt` — 9 Python packages including `audioop-lts` for Python 3.13 compatibility
- `GROQ_API_KEY` set in Streamlit Cloud Secrets

### Python 3.13 Compatibility

Streamlit Cloud runs Python 3.13, which removed the `audioop` stdlib module. The `pydub` library depends on `audioop` for audio processing. Resolution: added `audioop-lts` (community backport) to requirements.

---

## Changelog

All changes made during development on Feb 15, 2026.

### Bugs Fixed

| Issue | Root Cause | Fix |
|-------|-----------|-----|
| No transcription output | STT model `distil-whisper-large-v3-en` decommissioned by Groq | Changed to `whisper-large-v3-turbo` in `config.py` |
| No translation output | LLM model `llama3-70b-8192` deprecated by Groq | Changed to `llama-3.3-70b-versatile` in `config.py` |
| `ValueError: Frame does not match AudioResampler setup` | Output av.AudioFrame missing pts timestamps and mismatched format | Added pts counter, matched output frame format/layout to input |
| `ValueError: got 1920 bytes; need 3840 bytes` | Input is stereo (2ch × 960 samples = 3840 bytes) but output was mono (1920 bytes) | Added stereo↔mono conversion: average L+R on input, duplicate mono to L+R on output |
| Streamlit Cloud: `ModuleNotFoundError: No module named 'audioop'` | Python 3.13 removed `audioop` from stdlib; `pydub` depends on it | Added `audioop-lts` (community backport) to `requirements.txt` |
| Streamlit Cloud: `ModuleNotFoundError: No module named 'pyaudioop'` | `pyaudioop` package does not exist on PyPI | Replaced with `audioop-lts>=0.2.1` |
| Streamlit Cloud: `AttributeError: 'NoneType' object has no attribute 'is_alive'` | `streamlit-webrtc` 0.64.5 bug — `_polling_thread` is None during session teardown on reruns | Monkey-patched `SessionShutdownObserver.stop()` in `app.py` to handle None thread |

### Features Added

| Feature | Details |
|---------|---------|
| Initial 4 languages | Hindi, Telugu, Tamil, Malayalam with male + female voices |
| Expanded to 9 languages | Added Bengali, Gujarati, Kannada, Marathi, Urdu |
| Latency instrumentation | Timing for each pipeline stage (STT, Translate, TTS) logged per utterance |
| Live transcript display | Real-time transcript with original English and translated text in Streamlit UI |
| Streamlit Cloud deployment | Live at `live-classroom-translation-india.streamlit.app` |
| Repository setup | README.md, LICENSE (MIT), .env.example, comprehensive .gitignore |

### Model Changes

| Component | Original | Final |
|-----------|----------|-------|
| STT | `distil-whisper-large-v3-en` | `whisper-large-v3-turbo` |
| Translation LLM | `llama3-70b-8192` | `llama-3.3-70b-versatile` |

### Key Technical Decisions

| Decision | Reasoning |
|----------|-----------|
| Energy-based VAD over Silero VAD | Simpler, no ML dependency, sufficient for classroom (low ambient noise) |
| 3-second buffer | Balances latency vs. transcription quality; shorter buffers produce fragmented text |
| edge-tts over paid TTS | Free, supports all 9 Indian languages, acceptable quality for POC |
| `queue.Queue` over `asyncio.Queue` | WebRTC callback runs on a non-async thread; stdlib Queue is thread-safe |
| Daemon thread for pipeline | Auto-terminates when main thread exits; no cleanup needed |
| Mono internal processing | STT and TTS only need mono; stereo conversion at I/O boundaries only |

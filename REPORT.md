# Live Classroom Translation POC — Technical Report

**Live Demo:** [live-classroom-translation-india.streamlit.app](https://live-classroom-translation-india.streamlit.app/)
**Repository:** [github.com/velloreakash21/live-classroom-translation](https://github.com/velloreakash21/live-classroom-translation)

---

## Architecture

### High-Level System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER (Chrome)                               │
│                                                                             │
│  ┌──────────────┐      ┌─────────────────────┐      ┌──────────────────┐   │
│  │  Microphone   │─────→│   Streamlit WebRTC   │─────→│   Headphones     │   │
│  │  (Teacher)    │      │   (aiortc engine)    │      │   (Student)      │   │
│  └──────────────┘      └──────────┬──────────┘      └──────────────────┘   │
│                                   │  ↑                                      │
└───────────────────────────────────┼──┼──────────────────────────────────────┘
                              WebRTC │  │ WebRTC
                         audio frames│  │ translated frames
                                    ↓  │
┌───────────────────────────────────────────────────────────────────────────┐
│                        STREAMLIT SERVER (Python)                          │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    TranslationProcessor                              │  │
│  │                                                                      │  │
│  │  ┌──────────────┐    ┌────────────┐    ┌───────────────────────┐    │  │
│  │  │  recv()       │    │ processing │    │  _pipeline_worker()   │    │  │
│  │  │  (WebRTC      │───→│   _queue   │───→│  (Background Daemon   │    │  │
│  │  │   thread,     │    │ (maxsize=3)│    │   Thread)             │    │  │
│  │  │   ~50x/sec)   │    └────────────┘    │                       │    │  │
│  │  │               │                      │   ┌───────────────┐   │    │  │
│  │  │  • Stereo→Mono│                      │   │  1. Groq STT  │   │    │  │
│  │  │  • PCM Buffer │                      │   │  (Whisper)    │   │    │  │
│  │  │  • Energy VAD │                      │   └──────┬────────┘   │    │  │
│  │  │  • Silence det│                      │          ↓            │    │  │
│  │  │               │    ┌────────────┐    │   ┌───────────────┐   │    │  │
│  │  │               │←───│  output    │←───│   │  2. Groq LLM  │   │    │  │
│  │  │  Returns:     │    │   _queue   │    │   │  (Llama 3.3)  │   │    │  │
│  │  │  • Translated │    │(maxsize=500│    │   └──────┬────────┘   │    │  │
│  │  │    frame OR   │    └────────────┘    │          ↓            │    │  │
│  │  │  • Silence    │                      │   ┌───────────────┐   │    │  │
│  │  │    frame      │                      │   │  3. edge-tts  │   │    │  │
│  │  └──────────────┘                      │   │  (Neural TTS)  │   │    │  │
│  │                                         │   └───────────────┘   │    │  │
│  │                                         └───────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
│  ┌───────────────────────┐  ┌───────────────────────────────────────┐     │
│  │  Streamlit UI          │  │  Session State                        │     │
│  │  • Language selector   │  │  • processor instance                 │     │
│  │  • Voice gender toggle │  │  • transcript log                     │     │
│  │  • API key input       │  │  • language/voice config              │     │
│  │  • Live transcript log │  │  • WebRTC context                     │     │
│  └───────────────────────┘  └───────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────────┘
                    │                          │                    │
                    ↓                          ↓                    ↓
          ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
          │  Groq Cloud API  │    │  Groq Cloud API   │    │  Microsoft Edge  │
          │  ─────────────── │    │  ──────────────── │    │  TTS (CDN)       │
          │  Whisper Large   │    │  Llama 3.3 70B    │    │  ──────────────  │
          │  v3 Turbo        │    │  Versatile        │    │  Neural Voices   │
          │                  │    │                    │    │  (9 Indian langs)│
          │  Input: WAV bytes│    │  Input: English    │    │  Input: Text     │
          │  Output: English │    │  Output: Translated│    │  Output: MP3     │
          │         text     │    │          text      │    │         audio    │
          └─────────────────┘    └──────────────────┘    └──────────────────┘
```

### Threading Model

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│   WebRTC Media Thread              Background Daemon Thread       │
│   ───────────────────              ─────────────────────────      │
│                                                                   │
│   recv() called ~50x/sec           _pipeline_worker() loop:       │
│         │                                  │                      │
│         ├─ Append frame to buffer          ├─ Wait on proc_queue  │
│         │                                  │                      │
│         ├─ Check energy (VAD)              ├─ transcribe(wav)     │
│         │   if RMS > 500:                  │   → Groq Whisper API │
│         │     mark as speech               │   → ~0.45s           │
│         │                                  │                      │
│         ├─ If 3s buffer full OR            ├─ translate(text)     │
│         │   silence after speech:          │   → Groq LLM API    │
│         │     → put on proc_queue          │   → ~0.30s           │
│         │                                  │                      │
│         ├─ Check output_queue              ├─ synthesize(text)    │
│         │   → return translated frame      │   → edge-tts async  │
│         │   OR return silence frame        │   → ~1.10s           │
│         │                                  │                      │
│         └─ MUST return in <1ms             ├─ Convert MP3→PCM    │
│            (never blocks, never            │   → 960-sample frames│
│             makes API calls)               │                      │
│                                            └─ Put frames on       │
│                                               output_queue        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

- `recv()` runs on the WebRTC media thread ~50x/sec. Returns in <1ms. Never blocks, never makes API calls.
- A single **background daemon thread** runs the slow pipeline (STT → Translate → TTS).
- Two `queue.Queue` instances decouple the fast callback from slow API calls:
  - `processing_queue` (maxsize=3): audio chunks waiting for pipeline processing
  - `output_queue` (maxsize=500): translated PCM frames waiting for playback

### Audio Format Flow

```
┌──────────┐   s16, stereo   ┌──────────────┐   mono, int16   ┌────────────┐
│ Browser  │───  48kHz  ────→│ recv()       │──  numpy arr  ──→│ PCM Buffer │
│ Mic      │   av.AudioFrame │ stereo→mono  │   (avg L+R)     │ (3s=144K   │
└──────────┘                 └──────────────┘                  │  samples)  │
                                                               └─────┬──────┘
                                                                     │ WAV bytes
                                                                     ↓
┌──────────┐   MP3 bytes     ┌──────────────┐   translated    ┌────────────┐
│ edge-tts │←────────────────│ Groq LLM     │←── English ─────│ Groq       │
│ Neural   │   synthesis     │ Llama 3.3    │    text         │ Whisper    │
│ Voice    │                 │ Translation  │                  │ STT        │
└────┬─────┘                 └──────────────┘                  └────────────┘
     │ MP3
     ↓
┌──────────────┐  960-sample  ┌──────────────┐   stereo s16   ┌────────────┐
│ pydub decode │── frames ───→│ mono→stereo  │──  48kHz  ────→│ WebRTC     │
│ resample to  │   (20ms ea.) │ duplication  │   av.AudioFrame│ Output →   │
│ 48kHz mono   │              │ + pts stamps │                │ Headphones │
└──────────────┘              └──────────────┘                └────────────┘
```

### Classroom Deployment Architecture

#### Approach A: Cloud-Based

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLASSROOM                                     │
│                                                                         │
│   ┌──────────────┐                                                      │
│   │   TEACHER     │                                                      │
│   │  ┌─────────┐ │      WiFi / Internet                                 │
│   │  │ Lapel   │ │     ┌───────────────┐     ┌───────────────────────┐  │
│   │  │ Mic     │─┼────→│  Teacher's    │────→│  CLOUD SERVERS        │  │
│   │  └─────────┘ │     │  Laptop       │     │                       │  │
│   │              │     │  (Chrome +    │     │  Deepgram (STT)       │  │
│   │              │     │   Streamlit)  │←────│  Groq (Translation)   │  │
│   └──────────────┘     └───────────────┘     │  Azure TTS (Voices)   │  │
│                              │               └───────────────────────┘  │
│                              │ Translated audio                         │
│                              │ (per language)                           │
│                              ↓                                          │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │  AUDIO DISTRIBUTION (choose one)                                  │  │
│   │                                                                    │  │
│   │  Option 1: BYOD         Option 2: FM           Option 3: ESP32    │  │
│   │  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐    │  │
│   │  │📱 Student's  │      │📻 FM Trans-  │      │🔲 ESP32 WiFi │    │  │
│   │  │   Phone      │      │   mitters    │      │   Receiver   │    │  │
│   │  │   (WebSocket)│      │   (1/lang)   │      │   + OLED     │    │  │
│   │  │              │      │              │      │   + DAC      │    │  │
│   │  │  Select lang │      │  CH1=Hindi   │      │  Scroll to   │    │  │
│   │  │  on screen   │      │  CH2=Bengali │      │  select lang │    │  │
│   │  │  + earphones │      │  CH3=Kannada │      │  + earphones │    │  │
│   │  └──────────────┘      │  ...         │      └──────────────┘    │  │
│   │  Cost: ~₹150/student   │              │      Cost: ~₹1,600/unit  │  │
│   │                        │  FM Receiver │                           │  │
│   │                        │  per student │                           │  │
│   │                        │  (pre-tuned) │                           │  │
│   │                        └──────────────┘                           │  │
│   │                        Cost: ~₹1,200/unit                         │  │
│   └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Approach B: Edge (NVIDIA Jetson — Fully Offline)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLASSROOM                                     │
│                                                                         │
│   ┌──────────────┐     USB/WiFi     ┌────────────────────────────────┐  │
│   │   TEACHER     │                  │  NVIDIA JETSON ORIN NANO SUPER │  │
│   │  ┌─────────┐ │                  │  (67 TOPS, 8GB RAM)            │  │
│   │  │ Lapel   │─┼─────────────────→│                                │  │
│   │  │ Mic     │ │  audio stream    │  ┌────────────────────────┐    │  │
│   │  └─────────┘ │                  │  │ Whisper Small (TensorRT)│    │  │
│   │              │                  │  │ STT → ~0.3s             │    │  │
│   └──────────────┘                  │  └───────────┬────────────┘    │  │
│                                     │              ↓                  │  │
│                                     │  ┌────────────────────────┐    │  │
│                                     │  │ NLLB-200 (600M params) │    │  │
│                                     │  │ Translation → ~0.2s    │    │  │
│                                     │  └───────────┬────────────┘    │  │
│                                     │              ↓                  │  │
│                                     │  ┌────────────────────────┐    │  │
│                                     │  │ AI4Bharat Indic-TTS    │    │  │
│                                     │  │ (VITS) → ~0.3s         │    │  │
│                                     │  └───────────┬────────────┘    │  │
│                                     │              │                  │  │
│                                     │  All models run locally on GPU │  │
│                                     │  No internet required          │  │
│                                     │  Total latency: ~2.3s          │  │
│                                     └───────────────┬────────────────┘  │
│                                                     │                   │
│                              Translated audio       │                   │
│                              (per language)         ↓                   │
│                                           ┌──────────────────┐          │
│                                           │  WiFi Router     │          │
│                                           │  (Local network) │          │
│                                           └────────┬─────────┘          │
│                              ┌──────────┬──────────┼──────────┐         │
│                              ↓          ↓          ↓          ↓         │
│                          ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐        │
│                          │📱/🔲 │  │📱/🔲 │  │📱/🔲 │  │📱/🔲 │        │
│                          │Hindi │  │Bengali│  │Kannada│  │Tamil │        │
│                          └──────┘  └──────┘  └──────┘  └──────┘        │
│                            Students (phones, FM, or ESP32 receivers)    │
└─────────────────────────────────────────────────────────────────────────┘
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

> **Note:** All INR prices are estimated at ~₹85/USD as of Feb 2026. Actual prices may vary based on exchange rates and vendor pricing changes.

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
| **1 minute**              | ~₹0.15         |
| **1 hour**                | ~₹8.50         |
| **8-hour day**            | ~₹69           |
| **30-day month** (8h/day) | ~₹2,060        |

> A full classroom day (8 hours) of continuous live translation costs under ₹70.

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
| **Current (POC)** | **~5.0s** | — | ~₹8.50 | ~₹69 | ~₹2,060 |
| **Tier 1:** Streaming STT | **~1.7s** | 66% faster | ~₹13 | ~₹100 | ~₹3,060 |
| **Tier 2:** + Streaming TTS | **~0.85s** | 83% faster | ~₹42 | ~₹340 | ~₹10,200 |
| **Tier 3:** Full streaming | **~0.5s** | 90% faster | ~₹128 | ~₹1,020 | ~₹30,600 |

#### Per-Stage Latency Breakdown

| Stage | Current | Tier 1 | Tier 2 | Tier 3 |
|-------|---------|--------|--------|--------|
| Buffer wait | 3.00s | 0s | 0s | 0s |
| STT | 0.45s | 0.30s | 0.30s | 0.20s |
| Translation | 0.30s | 0.30s | 0.15s | 0.10s |
| TTS | 1.10s | 1.10s | 0.25s | 0.20s |
| Overhead | 0.15s | 0s | 0.15s | 0s |
| **Total** | **~5.0s** | **~1.7s** | **~0.85s** | **~0.5s** |

#### Tier 1 — Detailed Cost Breakdown (~₹13/hr)

Replace batch Groq Whisper with streaming Deepgram Nova-2. Eliminates the 3s buffer.

| Component | Service | Cost / Hour |
|-----------|---------|-------------|
| STT | Deepgram Nova-2 (streaming) | ~₹3.00 |
| Translation | Groq Llama 3.3 (batch) | ~₹5.20 |
| TTS | edge-tts (free) | ₹0 |
| **Total** | | **~₹8 → ~₹13** |

*What changes:* Replace `transcribe()` with Deepgram WebSocket; remove PCM buffer; let Deepgram handle VAD/endpointing.
*Effort:* Minimal — swap one API, remove buffer logic.

#### Tier 2 — Detailed Cost Breakdown (~₹42/hr)

Add Azure Neural TTS streaming and Groq streaming translation.

| Component | Service | Cost / Hour |
|-----------|---------|-------------|
| STT | Deepgram Nova-2 (streaming) | ~₹3.00 |
| Translation | Groq Llama 3.3 (streaming tokens) | ~₹5.20 |
| TTS | Azure Neural TTS (WebSocket) | ~₹32.60 |
| **Total** | | **~₹42** |

*TTS cost calculation:* ~150 words/min spoken → ~600 chars/min translated → 36,000 chars/hr × ₹1,360/1M chars = ~₹32.60/hr.
*What changes:* Add Azure TTS WebSocket connection; stream Groq response tokens; begin TTS as first sentence completes.
*Effort:* Moderate — new TTS integration, async pipeline restructuring.

#### Tier 3 — Detailed Cost Breakdown (~₹128/hr)

All services streaming via persistent WebSockets. Overlapping pipeline stages.

| Component | Service | Cost / Hour |
|-----------|---------|-------------|
| STT | Deepgram Nova-2 (streaming) | ~₹3.00 |
| Translation | Cerebras Inference (streaming) | ~₹5.50 |
| TTS | Cartesia Sonic (streaming) | ~₹119 |
| **Total** | | **~₹128** |

*TTS cost calculation:* ~36,000 chars/hr × ₹3.57/1K chars = ~₹119/hr (Cartesia is premium but ultra-low latency at ~90ms).
*Alternative:* ElevenLabs Turbo at ₹25.50/1K chars = ~₹918/hr (higher quality but significantly more expensive).
*What changes:* Full async WebSocket pipeline; all stages run concurrently; sentence boundary detection between STT and translation.
*Effort:* Full rewrite — new architecture, all new service integrations.

#### Cost vs. Latency Trade-off

```
Cost/hr:  ₹8.50 ──── ₹13 ──────────── ₹42 ──────────── ₹128
             │          │                   │                   │
Latency:   5.0s ──── 1.7s ──────────── 0.85s ──────────── 0.5s
             │          │                   │                   │
            POC      Tier 1             Tier 2             Tier 3
           (free     (streaming         (streaming         (full
            TTS)      STT only)          STT+TTS)          streaming)
```

> **Best value:** Tier 1 delivers a 66% latency reduction (5.0s → 1.7s) for only ~₹4.50/hr more — practically free at ~₹100/day.
> **Best experience:** Tier 2 achieves sub-second latency at ~₹340/day — suitable for production classroom use.

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

**Phase 1 — Quick win (5.0s → 1.7s, +~₹4.50/hr):**
- Replace Groq Whisper batch calls with **Deepgram Nova-2 streaming** WebSocket
- Remove the 3s PCM buffer; let Deepgram handle endpointing/VAD
- Keep Groq translation and edge-tts unchanged

**Phase 2 — Sub-second (1.7s → 0.85s, +~₹29/hr):**
- Add **Azure Neural TTS** via WebSocket (streaming playback)
- Enable **Groq streaming** response for translation
- Begin TTS synthesis as soon as first translated sentence is available

**Phase 3 — Near real-time (0.85s → 0.5s, +~₹86/hr):**
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

## Classroom Deployment Plan

This section covers end-to-end physical deployment in a real classroom — hardware, audio distribution to students, language selection UI, and two architectural approaches: **cloud-based** and **edge/on-premise**.

> **Note:** All prices are estimated as of Feb 2026 and converted at ~₹85/USD. Actual prices may vary based on vendor, quantity, location, and market conditions. Always verify current pricing before procurement.

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        CLASSROOM                            │
│                                                             │
│   ┌──────────┐     ┌──────────────┐     ┌──────────────┐   │
│   │ Teacher   │────→│ Server       │────→│ Students     │   │
│   │ (Mic +    │     │ (Cloud or    │     │ (Receivers + │   │
│   │  Laptop)  │     │  Jetson)     │     │  Earphones)  │   │
│   └──────────┘     └──────────────┘     └──────────────┘   │
│                           │                    │            │
│                     ┌─────┴─────┐        ┌─────┴─────┐     │
│                     │ STT →     │        │ WiFi / FM │     │
│                     │ Translate │        │ per-lang  │     │
│                     │ → TTS     │        │ channels  │     │
│                     └───────────┘        └───────────┘     │
└─────────────────────────────────────────────────────────────┘
```

---

### Approach A: Cloud-Based Deployment

The teacher's laptop captures audio, sends it to cloud APIs for processing, and streams translated audio to students over the local network or FM.

#### A1. Teacher Setup

| Item | Specification | Est. Cost |
|------|--------------|-----------|
| Laptop/Tablet | Any modern laptop running Chrome | Existing |
| Wireless lapel mic | Rode Wireless GO II or similar | ~₹15,000 |
| Internet connection | Min 5 Mbps upload (for API calls) | Existing |

The teacher opens the web app, clips on the lapel mic, and speaks naturally. No training required.

#### A2. Audio Distribution to Students

Three options for getting translated audio to each student:

**Option 1: Smartphones (BYOD) — Cheapest**

Students open a web URL on their phone, select their language, and listen through their own earphones.

| Item | Details | Cost per Student |
|------|---------|-----------------|
| Student's smartphone | BYOD (bring your own device) | ₹0 |
| Earphones/earbuds | Basic wired earbuds | ~₹150 |
| WiFi router | Classroom WiFi for all students | ~₹4,000 (one-time) |

*Architecture:* Server generates separate audio streams per language. Students connect via WebSocket and receive their selected language's audio in real-time.

*Pros:* Near-zero hardware cost. Easy language selection via UI on phone.
*Cons:* Requires each student to have a smartphone. Battery drain. Potential WiFi congestion with 30+ devices.

**Option 2: FM Radio Receivers — Most Reliable**

Each language is broadcast on a separate FM frequency. Students wear small FM receivers tuned to their language.

| Item | Details | Cost per Student |
|------|---------|-----------------|
| FM transmitter (multi-channel) | Retekess T130S or similar, 1 per language | ~₹2,500 each |
| FM receivers + earbuds | Retekess T130 receiver | ~₹1,200 each |
| Charging case (64-slot) | Retekess charging dock | ~₹12,000 (one-time) |

*Architecture:* Server outputs translated audio per language → each language feeds a separate FM transmitter → students wear receivers pre-tuned to their language's frequency.

| FM Channel | Language | Frequency |
|------------|----------|-----------|
| CH1 | Hindi | 87.5 MHz |
| CH2 | Bengali | 88.0 MHz |
| CH3 | Kannada | 88.5 MHz |
| CH4 | Tamil | 89.0 MHz |
| ... | ... | ... |

*Pros:* Extremely reliable. No WiFi needed. Works with 100+ students. Students just pick up a receiver — no phone needed.
*Cons:* Higher upfront cost. Language selection = picking the right receiver/channel. Students can't easily switch languages.

**Option 3: ESP32 WiFi Receivers — Custom Hardware, Best UX**

Custom-built WiFi audio receivers using ESP32 microcontrollers with a small OLED screen for language selection and a 3.5mm headphone jack.

| Item | Details | Cost per Unit |
|------|---------|--------------|
| ESP32-S3 module | WiFi + Bluetooth, I2S audio out | ~₹400 |
| PCM5102A I2S DAC | High-quality audio output | ~₹250 |
| 0.96" OLED display | Language selection menu | ~₹250 |
| 3D-printed case | Compact enclosure | ~₹150 |
| LiPo battery (500mAh) | ~8hr runtime | ~₹250 |
| Assembly + PCB | Per-unit manufacturing | ~₹300 |
| **Total per unit** | | **~₹1,600** |

*Architecture:* ESP32 connects to classroom WiFi → subscribes to a language-specific audio stream via WebSocket → decodes and plays through DAC → headphone jack.

*Student UX:* Power on → scroll OLED to select language → plug in earphones → listen.

*Pros:* Beautiful custom UX. Students scroll to select language on device. No smartphone needed. Rechargeable.
*Cons:* Requires custom hardware development. Lead time for manufacturing.

#### A3. Cloud Infrastructure Cost (per classroom, per month)

Assuming Tier 2 streaming pipeline, 6 hours/day, 22 days/month:

| Component | Cost / Month |
|-----------|-------------|
| Cloud APIs (Tier 2: Deepgram + Groq + Azure TTS) | ~₹5,600 |
| Streamlit Cloud hosting | Free |
| Internet (school WiFi) | Existing |
| **Total recurring** | **~₹5,600 / month** |

#### A4. Cloud Setup — Total One-Time Costs

| Classroom Size | Distribution Method | Hardware Cost | Recurring/Month |
|---------------|-------------------|--------------|----------------|
| 30 students | Smartphones (BYOD) | ~₹8,500 (router + earbuds) | ~₹5,600 |
| 30 students | FM receivers | ~₹63,500 (transmitters + receivers + charger) | ~₹5,600 |
| 30 students | ESP32 custom devices | ~₹52,000 (30 units + router) | ~₹5,600 |
| 60 students | FM receivers | ~₹1,15,000 | ~₹5,600 |
| 60 students | ESP32 custom devices | ~₹1,00,000 | ~₹5,600 |

---

### Approach B: Edge Deployment (NVIDIA Jetson — Zero Recurring Cost)

Run the entire pipeline locally on an NVIDIA Jetson device. No internet required after setup. Zero API costs.

#### B1. Hardware Stack

| Item | Specification | Est. Cost |
|------|--------------|-----------|
| **NVIDIA Jetson Orin Nano Super** | 67 TOPS, 8GB RAM, GPU-accelerated AI | ~₹33,000 |
| NVMe SSD (256GB) | For models + OS | ~₹2,500 |
| Power supply | 15W USB-C | Included |
| Wireless lapel mic | Rode Wireless GO II | ~₹15,000 |
| WiFi router (for student devices) | Dual-band, 50+ clients | ~₹4,000 |
| **Total server hardware** | | **~₹55,000** |

#### B2. On-Device AI Models

| Pipeline Stage | Model | Size | Jetson Performance |
|---------------|-------|------|--------------------|
| **STT** | Whisper Small (TensorRT) | 461MB | ~0.3s for 3s audio (3x faster via whisper_trt) |
| **STT (better)** | Whisper Medium (TensorRT) | 1.5GB | ~0.8s for 3s audio |
| **Translation** | NLLB-200 (Meta, distilled 600M) | 1.2GB | ~0.2s per sentence |
| **Translation (alt)** | IndicTrans2 (AI4Bharat, 1.1B) | 2.2GB | ~0.4s per sentence |
| **TTS** | AI4Bharat Indic-TTS (VITS) | ~200MB | ~0.3s per sentence |
| **TTS (alt)** | Piper TTS + Indic voices | ~100MB | ~0.1s per sentence |

All models fit in 8GB RAM. Total model footprint: ~2-4GB depending on configuration.

**Key projects for Jetson deployment:**
- [whisper_trt](https://github.com/NVIDIA-AI-IOT/whisper_trt) — NVIDIA's official Whisper TensorRT optimization (3x faster, 60% less memory)
- [AI4Bharat Indic-TTS](https://github.com/AI4Bharat/Indic-TTS) — Open-source TTS for 13 Indian languages
- [Indic Parler-TTS](https://huggingface.co/ai4bharat/indic-parler-tts) — Next-gen Indic TTS supporting 21 languages (Apache 2.0 license)

#### B3. Edge Pipeline Latency (Estimated)

| Stage | Cloud (Tier 2) | Jetson Orin Nano |
|-------|---------------|-----------------|
| Buffer/VAD | 0s (streaming) | 1.5s (reduced buffer) |
| STT | 0.30s | 0.30s (Whisper Small TRT) |
| Translation | 0.15s | 0.20s (NLLB-200) |
| TTS | 0.25s | 0.30s (Indic-TTS) |
| **Total** | **~0.85s** | **~2.3s** |

The Jetson is slower than cloud streaming APIs but has **zero recurring cost** and **no internet dependency**.

#### B4. Edge Setup — Total Costs

| Classroom Size | Distribution Method | One-Time Hardware | Recurring/Month |
|---------------|-------------------|------------------|----------------|
| 30 students | Smartphones (BYOD) | ~₹59,500 (Jetson + router + earbuds) | **₹0** |
| 30 students | FM receivers | ~₹1,08,500 (Jetson + FM system) | **₹0** |
| 30 students | ESP32 custom devices | ~₹1,03,000 (Jetson + ESP32s + router) | **₹0** |
| 60 students | FM receivers | ~₹1,60,000 | **₹0** |
| 60 students | ESP32 custom devices | ~₹1,51,000 | **₹0** |

---

### Cloud vs. Edge — Full Comparison

| Factor | Cloud (Approach A) | Edge / Jetson (Approach B) |
|--------|-------------------|---------------------------|
| **Latency (best)** | ~0.85s (Tier 2) | ~2.3s |
| **Latency (POC)** | ~5.0s | ~3.5s |
| **Recurring cost** | ₹5,600/month (Tier 2) | **₹0** |
| **Upfront cost (30 students, FM)** | ~₹63,500 | ~₹1,08,500 |
| **Break-even point** | — | ~8 months |
| **Internet required** | Yes (5 Mbps+) | **No** |
| **Voice quality** | Excellent (neural voices) | Good (open-source VITS) |
| **Languages** | 9 (expandable) | 13-21 (AI4Bharat models) |
| **Maintenance** | Zero (cloud-managed) | Occasional model updates |
| **Reliability** | Depends on internet | Fully offline, always works |
| **Scalability** | Unlimited classrooms | 1 Jetson per classroom |
| **Privacy** | Audio sent to cloud APIs | **All data stays local** |

#### Cost Projection Over Time (30 students, FM receivers)

| Duration | Cloud (Approach A) | Edge (Approach B) |
|----------|-------------------|-------------------|
| Setup (month 0) | ₹63,500 | ₹1,08,500 |
| After 6 months | ₹97,100 | ₹1,08,500 |
| **After 8 months** | **₹1,08,300** | **₹1,08,500** ← Break-even |
| After 1 year | ₹1,30,700 | ₹1,08,500 |
| After 2 years | ₹1,97,900 | ₹1,08,500 |
| After 3 years | ₹2,65,100 | ₹1,08,500 |

> **Verdict:** Edge pays for itself in ~8 months and saves ₹50,000+/year thereafter. Cloud is better for pilot/short-term. Edge wins for permanent installations.

---

### Student Language Selection UI

Regardless of cloud or edge, students need a way to select their language.

**For smartphone (BYOD) approach:**

A clean, mobile-first web UI served from the translation server:

```
┌─────────────────────────────┐
│   🎓 Classroom Translation  │
│                             │
│   Select your language:     │
│                             │
│   ┌───────────────────────┐ │
│   │  🇮🇳  Hindi           │ │
│   ├───────────────────────┤ │
│   │  🇮🇳  Bengali         │ │
│   ├───────────────────────┤ │
│   │  🇮🇳  Kannada         │ │
│   ├───────────────────────┤ │
│   │  🇮🇳  Tamil           │ │
│   ├───────────────────────┤ │
│   │  🇮🇳  Telugu          │ │
│   └───────────────────────┘ │
│                             │
│   Scan QR code to connect:  │
│   ┌─────────┐              │
│   │ QR CODE │              │
│   └─────────┘              │
└─────────────────────────────┘
```

- Teacher's screen displays a **QR code** with the classroom URL
- Students scan with phone camera → opens web app
- One-tap language selection → audio streams immediately
- No app install required — pure web (PWA)

**For FM receiver approach:**

- Receivers come pre-labeled: "CH1 = Hindi", "CH2 = Bengali", etc.
- Color-coded stickers on each receiver
- Poster on classroom wall with channel-language mapping

**For ESP32 custom device approach:**

- Power on → OLED shows language list
- Scroll with side button → press to select
- LED indicator shows connected status
- Auto-reconnects to classroom WiFi

---

### Recommended Deployment Configurations

**For a pilot program (1-2 classrooms, 3-6 months):**
→ **Cloud + Smartphones (BYOD)**
- Cheapest to start: ~₹8,500 setup + ~₹5,600/month
- Validates the concept before investing in hardware
- Easy to iterate on software

**For a permanent school installation (cost-sensitive):**
→ **Edge (Jetson) + FM receivers**
- One-time cost: ~₹1,08,500 per classroom
- Zero recurring costs, no internet needed
- Most reliable for rural/low-connectivity schools
- Break-even vs. cloud in 8 months

**For a premium school installation (best experience):**
→ **Cloud (Tier 2) + ESP32 custom devices**
- One-time: ~₹1,03,000 per classroom + ₹5,600/month
- Sub-second latency, excellent voice quality
- Beautiful student UX with OLED language selector
- Easy to add more languages remotely

**For a large-scale district deployment (100+ classrooms):**
→ **Edge (Jetson) + ESP32 custom devices, bulk manufactured**
- Per-classroom cost drops to ~₹68,000 at scale (bulk ESP32 + Jetson pricing)
- Zero recurring cost across all classrooms = massive savings
- Central management dashboard for model updates over school network
- Total for 100 classrooms: ~₹68,00,000 one-time vs. ₹67,20,000/year cloud

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

"""Audio processor for WebRTC streaming with translation pipeline."""

import queue
import time
import logging
import threading
import numpy as np
import av
from config import SAMPLE_RATE, CHANNELS, BUFFER_DURATION, SILENCE_THRESHOLD, FRAME_SIZE
from utils import pcm_to_wav_bytes, mp3_bytes_to_pcm_frames
from translation_pipeline import transcribe, translate, synthesize

logger = logging.getLogger(__name__)


class TranslationProcessor:
    """Processes audio frames: buffers input, runs translation pipeline, outputs translated audio.

    Threading model:
    - recv() is called on WebRTC thread ~50x/sec. MUST NOT block.
    - Background daemon thread runs the slow pipeline (STT -> translate -> TTS).
    - Two queues decouple the fast callback from slow API calls.
    """

    def __init__(self, api_key: str, target_language: str, voice_id: str):
        self.api_key = api_key
        self.target_language = target_language
        self.voice_id = voice_id

        # Queues for thread communication
        self.processing_queue = queue.Queue(maxsize=3)
        self.output_queue = queue.Queue(maxsize=500)

        # Audio buffer
        self._buffer = np.array([], dtype=np.int16)
        self._buffer_samples_target = SAMPLE_RATE * BUFFER_DURATION
        self._speech_detected = False

        # Track input frame properties for consistent output
        self._input_format = None
        self._input_layout = None
        self._input_sample_rate = None
        self._input_samples_per_frame = None
        self._input_channels = 1
        self._pts_counter = 0

        # Transcript log
        self._transcript_log = []
        self._log_lock = threading.Lock()

        # Background worker
        self._running = True
        self._worker = threading.Thread(target=self._pipeline_worker, daemon=True)
        self._worker.start()

    def recv(self, frame: av.AudioFrame) -> av.AudioFrame:
        """Process incoming audio frame. Called ~50x/sec on WebRTC thread.

        MUST return in <1ms. Never blocks, never makes API calls.
        Returns a frame matching the input frame's exact format to avoid
        AudioResampler mismatch errors in aiortc's opus encoder.
        """
        # Capture input frame properties on first call
        if self._input_format is None:
            self._input_format = frame.format.name
            self._input_layout = frame.layout.name
            self._input_sample_rate = frame.sample_rate
            self._input_samples_per_frame = frame.samples
            self._input_channels = len(frame.layout.channels) if frame.layout.channels else 1
            logger.info(
                f"Input frame: format={self._input_format}, layout={self._input_layout}, "
                f"rate={self._input_sample_rate}, samples={self._input_samples_per_frame}, "
                f"channels={self._input_channels}"
            )

        # Extract PCM data from input frame and convert to mono for buffering
        raw = frame.to_ndarray().flatten().astype(np.int16)
        if self._input_channels == 2:
            # Interleaved stereo (L,R,L,R,...) -> mono by averaging pairs
            pcm = ((raw[0::2].astype(np.int32) + raw[1::2].astype(np.int32)) // 2).astype(np.int16)
        else:
            pcm = raw
        self._buffer = np.concatenate([self._buffer, pcm])

        # Energy-based VAD
        energy = np.abs(pcm).mean()
        if energy > SILENCE_THRESHOLD:
            self._speech_detected = True

        # Check if we should process the buffer
        if len(self._buffer) >= self._buffer_samples_target:
            if self._speech_detected:
                # Put buffer into processing queue (non-blocking)
                try:
                    self.processing_queue.put_nowait(self._buffer.copy())
                except queue.Full:
                    # Drop oldest and add new
                    try:
                        self.processing_queue.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self.processing_queue.put_nowait(self._buffer.copy())
                    except queue.Full:
                        pass
            # Reset buffer
            self._buffer = np.array([], dtype=np.int16)
            self._speech_detected = False

        # Return translated audio frame or silence, matching input frame exactly
        n_samples = self._input_samples_per_frame or frame.samples

        try:
            out_pcm = self.output_queue.get_nowait()
            # Resize mono to match expected frame sample count
            if len(out_pcm) > n_samples:
                out_pcm = out_pcm[:n_samples]
            elif len(out_pcm) < n_samples:
                out_pcm = np.pad(out_pcm, (0, n_samples - len(out_pcm)))
        except queue.Empty:
            out_pcm = np.zeros(n_samples, dtype=np.int16)

        # If input is stereo, duplicate mono to both channels (interleaved L,R,L,R,...)
        if self._input_channels == 2:
            stereo = np.empty(n_samples * 2, dtype=np.int16)
            stereo[0::2] = out_pcm
            stereo[1::2] = out_pcm
            out_bytes = stereo.tobytes()
        else:
            out_bytes = out_pcm.tobytes()

        # Build output frame matching input frame properties exactly
        out_frame = av.AudioFrame(format="s16", layout=frame.layout.name, samples=n_samples)
        out_frame.sample_rate = frame.sample_rate
        out_frame.pts = self._pts_counter
        self._pts_counter += n_samples
        out_frame.planes[0].update(out_bytes)

        return out_frame

    def _pipeline_worker(self):
        """Background worker: runs STT -> translate -> TTS pipeline.

        Runs in a daemon thread with sequential processing.
        All exceptions caught and logged -- never crashes.
        """
        while self._running:
            try:
                # Wait for audio chunk (with timeout to check _running flag)
                try:
                    audio_chunk = self.processing_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                t0 = time.time()

                # Step 1: Transcribe
                wav_bytes = pcm_to_wav_bytes(audio_chunk)
                text = transcribe(wav_bytes, self.api_key)
                t1 = time.time()
                if not text or text.strip() == "":
                    logger.debug("Empty transcript, skipping")
                    continue

                # Step 2: Translate
                translated = translate(text, self.target_language, self.api_key)
                t2 = time.time()
                if not translated:
                    logger.warning("Translation returned empty, skipping")
                    continue

                # Log transcript
                with self._log_lock:
                    self._transcript_log.append((text, translated))

                # Step 3: Synthesize
                mp3_bytes = synthesize(translated, self.voice_id)
                t3 = time.time()
                if not mp3_bytes:
                    logger.warning("Synthesis returned empty, skipping")
                    continue

                # Step 4: Convert to PCM frames and enqueue
                frames = mp3_bytes_to_pcm_frames(mp3_bytes)
                for f in frames:
                    try:
                        self.output_queue.put_nowait(f)
                    except queue.Full:
                        break  # Output buffer full, skip remaining

                t4 = time.time()
                logger.info(
                    f"LATENCY: STT={t1-t0:.2f}s, Translate={t2-t1:.2f}s, "
                    f"TTS={t3-t2:.2f}s, Enqueue={t4-t3:.3f}s, "
                    f"TOTAL={t4-t0:.2f}s | \"{text[:50]}\" -> \"{translated[:50]}\""
                )

            except Exception as e:
                logger.error(f"Pipeline worker error: {e}", exc_info=True)

    def get_transcript_log(self) -> list:
        """Return list of (original, translated) text tuples."""
        with self._log_lock:
            return list(self._transcript_log)

    def stop(self):
        """Signal the worker thread to stop."""
        self._running = False

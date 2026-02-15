"""Streamlit app for Live Classroom Translation."""

import os
import time
import logging
import streamlit as st
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from dotenv import load_dotenv
from config import LANGUAGE_CONFIG
from audio_processor import TranslationProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="Live Classroom Translation",
    layout="wide",
)

st.title("Live Classroom Translation")
st.caption("Real-time English to Indian language translation")

# --- Sidebar ---
with st.sidebar:
    st.header("Settings")

    # API Key
    default_key = os.getenv("GROQ_API_KEY", "")
    api_key = st.text_input(
        "Groq API Key",
        value=default_key,
        type="password",
        help="Enter your Groq API key",
    )

    # Language selection
    language = st.selectbox(
        "Target Language",
        options=list(LANGUAGE_CONFIG.keys()),
    )

    # Voice gender
    gender = st.radio("Voice Gender", options=["Male", "Female"], horizontal=True)

    # Resolve voice ID
    lang_config = LANGUAGE_CONFIG[language]
    voice_id = lang_config["male_voice"] if gender == "Male" else lang_config["female_voice"]

    st.divider()
    st.markdown(f"**Voice:** `{voice_id}`")

# --- Validation ---
if not api_key:
    st.warning("Please enter your Groq API key in the sidebar to begin.")
    st.stop()

# --- WebRTC Streamer ---
# Store processor reference in session state for transcript access
if "processor" not in st.session_state:
    st.session_state.processor = None


def processor_factory():
    """Create a new TranslationProcessor with current settings."""
    processor = TranslationProcessor(
        api_key=api_key,
        target_language=language,
        voice_id=voice_id,
    )
    st.session_state.processor = processor
    return processor


ctx = webrtc_streamer(
    key="translation",
    mode=WebRtcMode.SENDRECV,
    audio_processor_factory=processor_factory,
    media_stream_constraints={"audio": True, "video": False},
    rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
    async_processing=True,
)

# --- Status & Transcript ---
if ctx.state.playing:
    st.markdown("**Status:** :red[Live]")

    transcript_container = st.empty()

    while ctx.state.playing:
        processor = st.session_state.get("processor")
        if processor:
            log = processor.get_transcript_log()
            if log:
                lines = []
                for original, translated in log:
                    lines.append(f"**Teacher (EN):** {original}")
                    lines.append(f"**Student ({lang_config['code'].upper()}):** {translated}")
                    lines.append("---")
                transcript_container.markdown("\n\n".join(lines))
        time.sleep(0.5)
else:
    st.markdown("**Status:** Idle")
    # Cleanup processor when stopped
    processor = st.session_state.get("processor")
    if processor:
        processor.stop()
        st.session_state.processor = None

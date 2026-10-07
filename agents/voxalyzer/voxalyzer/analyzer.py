import os
import shutil
import numpy as np
import time
import logging
import traceback
import gc
from pydub import AudioSegment
from tempfile import NamedTemporaryFile

import librosa
import onnxruntime as ort

from voxalyzer.memory import (
    cleanup_cuda_memory,
    cleanup_onnx_session,
    comprehensive_memory_cleanup
)
from voxalyzer.models import model_path
from voxalyzer.utils import get_best, to_ten, rescale, AnalyzeResult

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 200
MSD_EMBEDDING_MODEL_PATH = os.environ.get("MSD_MODEL", model_path("msd-musicnn-1.onnx"))
DISCOGS_EMBEDDING_MODEL_PATH = os.environ.get("DISCOGS_MODEL_PATH", model_path("discogs-effnet-bsdynamic-1.onnx"))

MOODS_MODEL_PATH = os.environ.get("MOODS_MODEL_PATH", model_path("msd-msd-musicnn-1.onnx"))

DEAM_MODEL_PATH = os.environ.get("DEAM_MODEL_PATH", model_path("deam-msd-musicnn-2.onnx"))
MIREX_MODEL_PATH = os.environ.get("MIREX_MODEL_PATH", model_path("moods_mirex-msd-musicnn-1.onnx"))

DANCEABILITY_MODEL_PATH = os.environ.get("DANCEABILITY_MODEL_PATH", model_path("danceability-discogs-effnet-1.onnx"))
AGGRESSIVE_MODEL_PATH = os.environ.get("AGGRESSIVE_MODEL_PATH", model_path("mood_aggressive-discogs-effnet-1.onnx"))
HAPPY_MODEL_PATH = os.environ.get("HAPPY_MODEL_PATH", model_path("mood_happy-discogs-effnet-1.onnx"))
PARTY_MODEL_PATH = os.environ.get("PARTY_MODEL_PATH", model_path("mood_party-discogs-effnet-1.onnx"))
RELAXED_MODEL_PATH = os.environ.get("RELAXED_MODEL_PATH", model_path("mood_relaxed-discogs-effnet-1.onnx"))
SAD_MODEL_PATH = os.environ.get("SAD_MODEL_PATH", model_path("mood_sad-discogs-effnet-1.onnx"))

ENGAGEMENT_MODEL_PATH = os.environ.get("ENGAGEMENT_MODEL_PATH", model_path("engagement_regression-discogs-effnet-1.onnx"))
TONAL_MODEL_PATH = os.environ.get("TONAL_MODEL_PATH", model_path("tonal_atonal-discogs-effnet-1.onnx"))
DARK_MODEL_PATH = os.environ.get("DARK_MODEL_PATH", model_path("nsynth_bright_dark-discogs-effnet-1.onnx"))
GENRE_MODEL_PATH = os.environ.get("GENRE_MODEL_PATH", model_path("mtg_jamendo_genre-discogs-effnet-1.onnx"))
MOODS_DISCOGS_MODEL_PATH = os.environ.get("MOODS_DISCOGS_MODEL_PATH", model_path("mtg_jamendo_moodtheme-discogs-effnet-1.onnx"))

AUDIO_LOAD_TIMEOUT = int(os.getenv("AUDIO_LOAD_TIMEOUT", "600"))  # Timeout in seconds for loading a single audio file.

MSD_FEATURE_LABELS = ['Deam']

DISCOGS_FEATURE_LABELS = ['Danceable', 'Aggressive', 'Happy', 'Party', 'Relaxed', 'Sad','Engagement', 'Tonal', 'Darkness']

MIREX_LABELS = [ "Exuberant", "Cheerful", "Melancholic", "Humorous", "Aggressive" ]

MSD_MOOD_LABELS = [
    'rock', 'pop', 'alternative', 'indie', 'electronic', 'female vocalists', 'dance', '00s', 'alternative rock', 'jazz',
    'beautiful', 'metal', 'chillout', 'male vocalists', 'classic rock', 'soul', 'indie rock', 'Mellow', 'electronica', '80s',
    'folk', '90s', 'chill', 'instrumental', 'punk', 'oldies', 'blues', 'hard rock', 'ambient', 'acoustic', 'experimental',
    'female vocalist', 'guitar', 'Hip-Hop', '70s', 'party', 'country', 'easy listening', 'sexy', 'catchy', 'funk', 'electro',
    'heavy metal', 'Progressive rock', '60s', 'rnb', 'indie pop', 'sad', 'House', 'happy'
]

DISCOGS_GENRE_LABELS = [
    "60s", "70s", "80s", "90s", "acidjazz", "alternative", "alternativerock", "ambient", "atmospheric",
    "blues", "bluesrock", "bossanova", "breakbeat", "celtic", "chanson", "chillout", "choir",
    "classical", "classicrock", "club", "contemporary", "country", "dance", "darkambient", "darkwave",
    "deephouse", "disco", "downtempo", "drumnbass", "dub", "dubstep", "easylistening", "edm",
    "electronic", "electronica", "electropop", "ethno", "eurodance", "experimental",
    "folk", "funk", "fusion", "groove", "grunge", "hard", "hardrock", "hiphop", "house",
    "idm", "improvisation", "indie", "industrial", "instrumentalpop", "instrumentalrock", "jazz", "jazzfusion",
    "latin", "lounge", "medieval", "metal", "minimal", "newage", "newwave", "orchestral", "pop", "popfolk",
    "poprock", "postrock", "progressive", "psychedelic", "punkrock", "rap", "reggae", "rnb", "rock", "rocknroll",
    "singersongwriter", "soul", "soundtrack", "swing", "symphonic", "synthpop", "techno", "trance", "triphop",
    "world", "worldfusion"
]

DISCOGS_MOODS_LABELS = [
    "action", "adventure", "advertising", "background", "ballad", "calm", "children", "christmas",
    "commercial", "cool", "corporate", "dark", "deep", "documentary", "drama", "dramatic", "dream",
    "emotional", "energetic", "epic", "fast", "film", "fun", "funny", "game", "groovy", "happy",
    "heavy", "holiday", "hopeful", "inspiring", "love", "meditative", "melancholic", "melodic", "motivational",
    "movie", "nature", "party", "positive", "powerful", "relaxing", "retro", "romantic", "sad", "sexy",
    "slow", "soft", "soundscape", "space", "sport", "summer", "trailer", "travel", "upbeat", "uplifting"
]

DEFINED_TENSORS = {
    # Takes spectrograms, outputs embeddings
    'Embedding_msd': {
        'model': MSD_EMBEDDING_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/dense/BiasAdd:0'
    },
    'Embedding_discogs': {
        'model': DISCOGS_EMBEDDING_MODEL_PATH,
        'input': 'serving_default_melspectrogram:0',
        'output': 'embeddings'
    },

    # Takes embeddings, outputs mood predictions
    'Moods': {
        'model': MOODS_MODEL_PATH,
        'input': 'serving_default_model_Placeholder:0',
        'output': 'PartitionedCall:0'
    },
    'Deam': {
        'model': DEAM_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Identity:0'
    },
    'Danceable': {
        'model': DANCEABILITY_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 0
    },
    'Aggressive': {
        'model': AGGRESSIVE_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 0
    },
    'Happy': {
        'model': HAPPY_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 0
    },
    'Party': {
        'model': PARTY_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 1
    },
    'Relaxed': {
        'model': RELAXED_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 1
    },
    'Sad': {
        'model': SAD_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 1
    },
    'Mirex': {
        'model': MIREX_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'PartitionedCall'
    },
    'Engagement': {
        'model': ENGAGEMENT_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Identity:0'
    },
    'Tonal': {
        'model': TONAL_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 1
    },
    'Darkness': {
        'model': DARK_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'model/Softmax:0',
        'outputIndex': 1
    },
    'Genre': {
        'model': GENRE_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'activations'
    },
    'Discogs_moods': {
        'model': MOODS_DISCOGS_MODEL_PATH,
        'input': 'model/Placeholder:0',
        'output': 'activations'
    }
}

class SessionHandler:
    """
    Recreate ONNX Runtime sessions every N tracks to prevent cumulative memory leaks.

    Even with proper cleanup, ONNX Runtime sessions can accumulate memory over many
    inferences due to internal caching and fragmentation. This class tracks usage
    and recreates sessions periodically.
    """
    onnx_sessions = None

    def __init__(self, recycle_interval: int = 20):
        """
        Initialize session recycler.

        Args:
            recycle_interval: Number of uses before recycling (default: 20 tracks)
        """
        self.recycle_interval = recycle_interval
        self.use_count = 0

    def get_session(self):
        if self.onnx_sessions is None:
            logger.info("Lazy-loading Essentia models")
            self.onnx_sessions = load_onnx_sessions()
        elif self.should_recycle():
            logger.info(f"Recycling ONNX sessions after {self.get_use_count()} tracks")
            self._session_cleanup()

            # Recreate sessions
            self.onnx_sessions = load_onnx_sessions()

            self.mark_recycled()

        return self.onnx_sessions

    def _session_cleanup(self):
        # Use comprehensive cleanup during session recycling
        for model_name, session in self.onnx_sessions.items():
            cleanup_onnx_session(session, model_name)

        self.onnx_sessions= None
        gc.collect()

        try:
            # Cleanup CUDA memory
            comprehensive_memory_cleanup(force_cuda=True, reset_onnx_pool=True)
            logger.debug("Final comprehensive cleanup completed (finally block)")
        except Exception as e:
            logger.warning(f"Error during final comprehensive cleanup: {e}")

    def close_session(self):
        if self.onnx_sessions:
            logger.info(f"Cleaning up {len(self.onnx_sessions)} Essentia model sessions (finally block)")
            self._session_cleanup()

    def increment(self) -> None:
        """Increment the usage counter (call after each use)."""
        self.use_count += 1

    def should_recycle(self) -> bool:
        """
        Check if session should be recycled based on usage count.

        Returns:
            True if use_count >= recycle_interval
        """
        return self.use_count >= self.recycle_interval

    def mark_recycled(self) -> None:
        """Reset the counter after recycling (call after creating new session)."""
        old_count = self.use_count
        self.use_count = 0
        logger.info(f"Session recycled after {old_count} uses")

    def get_use_count(self) -> int:
        """Get current usage count."""
        return self.use_count

    def reset(self) -> None:
        """Reset counter to zero (e.g., at start of new album)."""
        self.use_count = 0

# --- Utility Functions ---
def clean_temp(temp_dir):
    os.makedirs(temp_dir, exist_ok=True)
    for filename in os.listdir(temp_dir):
        file_path = os.path.join(temp_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            logger.warning(f"Could not remove {file_path} from {temp_dir}: {e}")


# --- Core Analysis Functions ---

def _find_onnx_name(candidate_name, names):
    """Try several heuristics to match a TF-style tensor name to an ONNX input/output name."""
    if candidate_name in names:
        return candidate_name
    # strip trailing :0
    stripped = candidate_name.split(':')[0]
    if stripped in names:
        return stripped
    # try last part after '/'
    last = stripped.split('/')[-1]
    if last in names:
        return last
    # try replacing '/' with '_'
    alt = stripped.replace('/', '_')
    if alt in names:
        return alt
    # fallback: return first name
    return names[0] if names else None


def run_inference(onnx_session, feed_dict, output_tensor_name=None, fallback_model=None):
    try:
        """Run inference on an ONNX Runtime session.
    
        onnx_session: ort.InferenceSession
        feed_dict: dict mapping possible tensor names to numpy arrays
        output_tensor_name: optional expected output name (TF-style). If None, use first output.
        """
        # Build input name -> value map for ONNX

        input_meta = onnx_session.get_inputs()
        input_names = [i.name for i in input_meta]
        mapped = {}
        logger.debug(f"ONNX session inputs: {input_names}")
        for key, val in feed_dict.items():
            onnx_name = _find_onnx_name(key, input_names)
            if onnx_name is None:
                logger.error(f"Could not map input name '{key}' to any ONNX input names: {input_names}")
                return None
            mapped[onnx_name] = val

        # Determine outputs
        output_meta = onnx_session.get_outputs()
        output_names = [o.name for o in output_meta]
        logger.debug(f"ONNX session outputs: {output_names}")
        if output_tensor_name:
            onnx_output_name = _find_onnx_name(output_tensor_name, output_names)
        else:
            onnx_output_name = output_names[0] if output_names else None

        if onnx_output_name is None:
            logger.error("No ONNX output name available to run inference.")
            return None

        # Run and return numpy array
        result = onnx_session.run([onnx_output_name], mapped)
        # onnxruntime returns a list of outputs in the same order
        return result[0] if isinstance(result, list) and len(result) > 0 else result

    except ort.capi.onnxruntime_pybind11_state.RuntimeException as e:
        if fallback_model is not None and "Failed to allocate memory" in str(e):
            logger.warning("GPU OOM detected during embedding inference, attempting CPU fallback...")

            # Use comprehensive cleanup for OOM errors
            comprehensive_memory_cleanup(force_cuda=True, reset_onnx_pool=True)

            # Create CPU session
            embedding_sess = ort.InferenceSession(fallback_model, providers=['CPUExecutionProvider'])

            # Retry with CPU session
            return run_inference(embedding_sess, feed_dict, output_tensor_name)
            logger.info("Successfully completed embedding inference on CPU after OOM")
        else:
            raise


def sigmoid(x):
    """Numerically stable sigmoid function."""
    return 1 / (1 + np.exp(-x))


def robust_load_audio_with_fallback(file_path, target_sr=16000):
    """
    Attempts to load an audio file directly with Librosa. If it fails or
    results in an empty audio signal, it falls back to a more robust method
    using pydub (and ffmpeg) to convert the file to a temporary WAV before loading.
    """
    audio = None
    sr = None

    # --- Primary Method: Direct Librosa Load ---
    try:
        audio, sr = librosa.load(file_path, sr=target_sr, mono=True, duration=AUDIO_LOAD_TIMEOUT)

        # An empty audio signal is a failure condition, so we raise an error to trigger the fallback.
        if audio is None or audio.size == 0:
            raise ValueError("Librosa returned an empty audio signal.")

        logger.debug(f"Successfully loaded {os.path.basename(file_path)} directly with Librosa.")
        return audio, sr

    except Exception as e_direct_load:
        logger.warning(f"Direct librosa load failed for {os.path.basename(file_path)}: {e_direct_load}. Attempting fallback conversion.")

    # --- Fallback Method: Convert to WAV with pydub ---
    temp_wav_path = None
    try:
        # Check the audio content with pydub before converting
        # Use more robust parameters for problematic codecs
        audio_segment = AudioSegment.from_file(
            file_path,
            # Add parameters to help with codec detection issues
            parameters=[
                "-analyzeduration", "10M",  # Increase analysis duration
                "-probesize", "10M",  # Increase probe size
                "-ignore_unknown",  # Ignore unknown streams
                "-err_detect", "ignore_err",  # Ignore decode errors
                "-ac", "2"  # Force downmix to stereo to handle multichannel files
            ]
        )
        if len(audio_segment) == 0:
            logger.error(f"Pydub loaded a zero-duration audio segment from {os.path.basename(file_path)}. The file is likely corrupt or empty.")
            return None, None

        with NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav_file:
            temp_wav_path = temp_wav_file.name

        # --- MEMORY OPTIMIZATION FOR LARGE FILES ---
        # Resample and convert to mono during export to create a much smaller temp file.
        # This is critical for handling very large source files without running out of memory.
        logger.info(f"Fallback: Pre-processing {os.path.basename(file_path)} to a smaller WAV for safe loading...")
        processed_segment = audio_segment.set_frame_rate(target_sr).set_channels(1)
        # Use more robust export parameters
        processed_segment.export(
            temp_wav_path,
            format="wav",
            parameters=[
                "-codec:a", "pcm_s16le",  # Fix the typo: was pcm_s0le, should be pcm_s16le
                "-ar", str(target_sr),  # Set sample rate explicitly
                "-ac", "1"  # Set mono explicitly
            ]
        )

        logger.info(f"Fallback: Converted {os.path.basename(file_path)} to temporary WAV for robust loading.")

        # Load the safe, downsampled WAV file
        audio, sr = librosa.load(temp_wav_path, sr=target_sr, mono=True, duration=AUDIO_LOAD_TIMEOUT)

        # Final check on the fallback's output for silence or emptiness
        if audio is None or audio.size == 0 or not np.any(audio):
            logger.error(f"Fallback method also resulted in an empty or silent audio signal for {os.path.basename(file_path)}.")
            return None, None

        return audio, sr

    except Exception as e_fallback:
        logger.error(f"Fallback loading method also failed for {os.path.basename(file_path)}: {e_fallback}")
        return None, None
    finally:
        # Clean up the temporary WAV file if it was created
        if temp_wav_path and os.path.exists(temp_wav_path):
            os.remove(temp_wav_path)


def _get_provider_options():
    available_providers = ort.get_available_providers()
    provider_options = []

    if 'CUDAExecutionProvider' in available_providers:
        # Get GPU device ID from environment or default to 0
        gpu_device_id = 0
        cuda_visible = os.environ.get('CUDA_VISIBLE_DEVICES', '')
        if cuda_visible and cuda_visible != '-1':
            gpu_device_id = 0

        cuda_options = {
            'device_id': gpu_device_id,
            'arena_extend_strategy': 'kSameAsRequested',  # Prevent memory fragmentation
            'cudnn_conv_algo_search': 'EXHAUSTIVE',
            'do_copy_in_default_stream': True,
        }
        provider_options.append(('CUDAExecutionProvider', cuda_options))
        logger.debug(f"CUDA provider available - attempting to use GPU for analysis (device_id={gpu_device_id})")

    if 'DmlExecutionProvider' in available_providers:
        provider_options.append(('DmlExecutionProvider', {}))
        logger.debug("DirectML provider available")

    provider_options.append(('CPUExecutionProvider', {}))

    if not any(p[0] in ['CUDAExecutionProvider', 'DmlExecutionProvider'] for p in provider_options):
        logger.info("GPU providers (CUDA/DirectML) not available - using CPU only")

    return provider_options


# Prepare Spectrograms ---
def prepare_spectrograms_unified(audio, sr):
    # 1. Common Mel-spectrogram calculation (The expensive part)
    # Both models use these exact settings
    n_mels, hop_length, n_fft = 96, 256, 512

    mel_spec = librosa.feature.melspectrogram(
        y=audio, sr=sr, n_fft=n_fft, hop_length=hop_length,
        n_mels=n_mels, window='hann', center=False,
        power=2.0, norm='slaney', htk=False
    )
    log_mel_spec = np.log10(1 + 10000 * mel_spec).astype(np.float32)

    # 2. Slice for MSD (frame_size = 187)
    msd_patches = _slice_patches(log_mel_spec, frame_size=187)

    # 3. Slice for Discogs (frame_size = 128)
    discogs_patches = _slice_patches(log_mel_spec, frame_size=128)

    del log_mel_spec, mel_spec

    return msd_patches, discogs_patches


def _slice_patches(spec, frame_size):
    # Helper to handle the slicing and transposing
    patches = [spec[:, i:i + frame_size] for i in range(0, spec.shape[1] - frame_size + 1, frame_size)]
    if not patches:
        return None
    # Returns [batch, time, freq]
    return np.array(patches).transpose(0, 2, 1)


def _extract_features_librosa(audio, sr):
    tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
    average_energy = np.mean(librosa.feature.rms(y=audio))

    # Improved key/scale detection
    chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)
    key_vals = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    major_profile = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1])
    minor_profile = np.array([1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0])

    major_correlations = np.array([np.corrcoef(chroma_mean, np.roll(major_profile, i))[0, 1] for i in range(12)])
    minor_correlations = np.array([np.corrcoef(chroma_mean, np.roll(minor_profile, i))[0, 1] for i in range(12)])

    major_key_idx = np.argmax(major_correlations)
    minor_key_idx = np.argmax(minor_correlations)

    if major_correlations[major_key_idx] > minor_correlations[minor_key_idx]:
        musical_key = key_vals[major_key_idx]
        scale = 'major'
    else:
        musical_key = key_vals[minor_key_idx]
        scale = 'minor'

    return {'bpm': int(round(float(tempo.item()))),
            'energy': to_ten(float(average_energy)),
            'musical_key': musical_key,
            'scale': scale}


def analyze_track(file_path, onnx_sessions, top_n_moods=3):
    """
    Analyzes a single track using ONNX Runtime for inference.

    Args:
        file_path: Path to audio file
        mood_labels_list: List of mood labels
        onnx_sessions: Dict of pre-loaded ONNX sessions (for album-level reuse)
    """
    logger.info(f"Starting analysis for: {os.path.basename(file_path)}")

    # --- 1. Load Audio and Compute Basic Features ---
    audio, sr = robust_load_audio_with_fallback(file_path, target_sr=16000)

    if audio is None or not np.any(audio) or audio.size == 0:
        logger.warning(f"Could not load a valid audio signal for {os.path.basename(file_path)} after all attempts. Skipping track.")
        return None, None

    features = _extract_features_librosa(audio, sr)

    categories = {"Energy" : features.pop('energy')}

    # --- 2. Prepare Spectrograms ---
    try:
        final_patches_msd, final_patches_discogs = prepare_spectrograms_unified(audio, sr)
    except Exception as e:
        logger.error(f"MSD Spectrogram creation failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None

    # --- 3. Run Main Models (Embedding and Prediction) ---
    # Initialize variables for cleanup in finally block - MUST be before try block
    embedding_msd_sess = None
    moods_sess = None

    try:
        # Use pre-loaded session
        embedding_msd_sess = onnx_sessions['Embedding_msd']
        tensor = DEFINED_TENSORS['Embedding_msd']

        embeddings_msd_per_patch = run_inference(embedding_msd_sess, {tensor['input']: final_patches_msd}, tensor['output'],
                                                 fallback_model=tensor['model'])

    except Exception as e:
        logger.error(f"MSD model inference failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None

    try:
        # Use pre-loaded session
        moods_sess = onnx_sessions['Moods']
        tensor = DEFINED_TENSORS['Moods']

        mood_logits = run_inference(moods_sess, {tensor['input']: embeddings_msd_per_patch}, tensor['output'], fallback_model=tensor['model'])

        averaged_logits = np.mean(mood_logits, axis=0)
        # Apply sigmoid to convert raw model outputs (logits) into probabilities
        #final_mood_predictions = sigmoid(averaged_logits)
        #moods = {label: float(score) for label, score in zip(MSD_MOOD_LABELS, final_mood_predictions)}
        #moods = dict(sorted(moods.items(), key=lambda i: i[1], reverse=True)[:top_n_moods])

        moods = get_best(MSD_MOOD_LABELS, averaged_logits)

    except Exception as e:
        logger.error(f"MSD Moods inference failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None
    finally:
        del mood_logits, averaged_logits#, final_mood_predictions

    #MIREX
    try:
        # Use pre-loaded session
        mirex_sess = onnx_sessions['Mirex']
        tensor = DEFINED_TENSORS['Mirex']

        mirex_logits = run_inference(mirex_sess, {tensor['input']: embeddings_msd_per_patch}, tensor['output'], fallback_model=tensor['model'])

        averaged_logits = np.mean(mirex_logits, axis=0)

        # Apply sigmoid to convert raw model outputs (logits) into probabilities
        #final_mirex_predictions = sigmoid(averaged_logits)
        #tags = {label: float(score) for label, score in zip(MIREX_LABELS, final_mirex_predictions)}
        #tags = dict(sorted(tags.items(), key=lambda i: i[1], reverse=True)[:top_n_moods])

        dominant_idx = np.argmax(averaged_logits)
        tag = MIREX_LABELS[dominant_idx]

    except Exception as e:
        logger.error(f"MSD Tags inference failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None
    finally:
        del mirex_logits, averaged_logits#, final_mirex_predictions



    # --- 4. Run MSD Feature Models ---
    for key in MSD_FEATURE_LABELS:
        other_sess = None
        try:
            # Use pre-loaded sessions
            other_sess = onnx_sessions[key]
            tensor = DEFINED_TENSORS[key]

            probabilities_per_patch = run_inference(other_sess, {tensor['input']: embeddings_msd_per_patch}, tensor['output'], fallback_model=tensor['model'])

            if probabilities_per_patch is None:
                categories[key] = None
            else:
                if isinstance(probabilities_per_patch, np.ndarray) and probabilities_per_patch.ndim == 2 and probabilities_per_patch.shape[1] == 2:
                    # Using the CLASS_INDEX_MAP to select the correct probability
                    if key == 'Deam':
                        class_probs = probabilities_per_patch[:, 0]
                        categories['Valence'] = round(rescale(float(np.mean(class_probs))),1) # map from 1-9 to 0-10

                        class_probs = probabilities_per_patch[:, 1]
                        categories['Arousal'] = round(rescale(float(np.mean(class_probs))),1) # map from 1-9 to 0-10
                    else:
                        positive_class_index = tensor.get("outputIndex", 0)
                        class_probs = probabilities_per_patch[:, positive_class_index]
                        categories[key] = to_ten(np.mean(class_probs))
                elif isinstance(probabilities_per_patch, np.ndarray) and probabilities_per_patch.ndim == 2 and probabilities_per_patch.shape[1] == 1:
                    categories[key] = to_ten(np.mean(probabilities_per_patch))
                else:
                    categories[key] = None

        except Exception as e:
            logger.error(f"Error predicting '{key}' for {os.path.basename(file_path)}: {e}", exc_info=True)
            categories[key] = None
        finally:
            del probabilities_per_patch

    # --- 5. Run Discogs Feature Models ---
    try:
        # Use pre-loaded session
        tensor = DEFINED_TENSORS['Embedding_discogs']
        embedding_discogs_sess = onnx_sessions['Embedding_discogs']

        embeddings_discogs_per_patch = run_inference(embedding_discogs_sess, {tensor['input']: final_patches_discogs}, tensor['output'],
                                                     fallback_model=tensor['model'])

    except Exception as e:
        logger.error(f"Discogs model inference failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None

    for key in DISCOGS_FEATURE_LABELS:
        other_sess = None
        try:
            # Use pre-loaded sessions
            other_sess = onnx_sessions[key]
            tensor = DEFINED_TENSORS[key]

            probabilities_per_patch = run_inference(other_sess, {tensor['input']: embeddings_discogs_per_patch}, tensor['output'], fallback_model=tensor['model'])

            if probabilities_per_patch is None:
                categories[key] = None
            else:
                if isinstance(probabilities_per_patch, np.ndarray) and probabilities_per_patch.ndim == 2 and probabilities_per_patch.shape[1] == 2:
                    # Using the CLASS_INDEX_MAP to select the correct probability
                    positive_class_index = tensor.get("outputIndex", 0)
                    class_probs = probabilities_per_patch[:, positive_class_index]
                    categories[key] = to_ten(np.mean(class_probs))
                elif isinstance(probabilities_per_patch, np.ndarray) and probabilities_per_patch.ndim == 2 and probabilities_per_patch.shape[1] == 1:
                    categories[key] = to_ten(np.mean(probabilities_per_patch))
                else:
                    categories[key] = None

        except Exception as e:
            logger.error(f"Error predicting '{key}' for {os.path.basename(file_path)}: {e}", exc_info=True)
            categories[key] = None
        finally:
            del probabilities_per_patch


    try:
        # Use pre-loaded session
        genre_sess = onnx_sessions['Genre']
        tensor = DEFINED_TENSORS['Genre']

        genre_logits = run_inference(genre_sess, {tensor['input']: embeddings_discogs_per_patch}, tensor['output'], fallback_model=tensor['model'])

        averaged_logits = np.mean(genre_logits, axis=0)

        # Apply sigmoid to convert raw model outputs (logits) into probabilities
        # final_genre_predictions = sigmoid(averaged_logits)
        # genres = {label: float(score) for label, score in zip(DISCOGS_GENRE_LABELS, final_genre_predictions)}
        # genres = dict(sorted(genres.items(), key=lambda i: i[1], reverse=True)[:1])

        # Create a list of (Genre, Probability) pairs
        genres = get_best(DISCOGS_GENRE_LABELS,averaged_logits)

    except Exception as e:
        logger.error(f"Discogs Genres inference failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None
    finally:
        del genre_logits,averaged_logits#,final_genre_predictions

    try:
        # Use pre-loaded session
        discog_moods_sess = onnx_sessions['Discogs_moods']
        tensor = DEFINED_TENSORS['Discogs_moods']

        discog_moods_logits = run_inference(discog_moods_sess, {tensor['input']: embeddings_discogs_per_patch}, tensor['output'], fallback_model=tensor['model'])

        averaged_logits = np.mean(discog_moods_logits, axis=0)
        # Apply sigmoid to convert raw model outputs (logits) into probabilities

        #final_discog_moods_predictions = sigmoid(averaged_logits)
        #discog_moods = {label: float(score) for label, score in zip(DISCOGS_MOODS_LABELS, final_discog_moods_predictions)
        #discog_moods = dict(sorted(discog_moods.items(), key=lambda i: i[1], reverse=True)[:top_n_moods])

        discog_moods = get_best(DISCOGS_MOODS_LABELS, averaged_logits)

    except Exception as e:
        logger.error(f"Discogs Moods inference failed for {os.path.basename(file_path)}: {e}", exc_info=True)
        return None, None
    finally:
        del discog_moods_logits,averaged_logits#,final_discog_moods_predictions

    # --- 5. Final Aggregation for Storage ---
    processed_embeddings = np.mean(embeddings_msd_per_patch, axis=0)

    # CRITICAL: Clean up large tensors before return
    try:
        # Clean up all large intermediate variables
        del embeddings_msd_per_patch, embeddings_discogs_per_patch, audio, final_patches_msd, final_patches_discogs

        import gc
        gc.collect()
        # Use comprehensive cleanup for successful analysis
        comprehensive_memory_cleanup(force_cuda=False, reset_onnx_pool=False)
    except Exception as cleanup_error:
        logger.warning(f"Error during final tensor cleanup: {cleanup_error}")

    return {"moods": moods, "genres": genres,"discog_moods": discog_moods, "tags": [tag], "categories": categories, **features}, processed_embeddings


def load_onnx_sessions():
    # Configure provider options for GPU memory management (used for main and secondary models)
    provider_options = _get_provider_options()
    onnx_sessions = {}

    sess_options = ort.SessionOptions()
    # Set to level 1 (Basic) instead of level 99 (All)
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    #sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    try:
        for model_name, model_info in DEFINED_TENSORS.items():
            try:
                onnx_sessions[model_name] = ort.InferenceSession(
                    model_info['model'],
                    sess_options= sess_options,
                    providers=[p[0] for p in provider_options],
                    provider_options=[p[1] for p in provider_options]
                )
            except Exception:
                onnx_sessions[model_name] = ort.InferenceSession(
                    model_info['model'],
                    providers=['CPUExecutionProvider']
                )
        logger.info(f"✓ Loaded {len(onnx_sessions)} Essentia model sessions")
    except Exception as e:
        logger.error(f"Failed to load Essentia models: {e}")
        onnx_sessions = None

    return onnx_sessions

def begin_session(model_reload=False):
    recycle_interval = 1 if model_reload else 20
    logger.info(f"ONNX session recycling: every {recycle_interval} song(s) (PER_SONG_MODEL_RELOAD={model_reload})")
    return SessionHandler(recycle_interval=recycle_interval)

def end_session(session:SessionHandler):
    session.close_session()

def analyze_file(path: str, session_handler:SessionHandler = None, force = False) -> AnalyzeResult:
    needs_analysis = True  # TODO
    # Analysis (only if needed)
    if needs_analysis or force:
        # Lazy-load models on first song that needs analysis
        onnx_sessions = session_handler.get_session()

        analysis, embedding = analyze_track(path, onnx_sessions)

        if analysis is None:
            logger.warning(f"Skipping track {path} as analysis returned None.")
            return None

        # Increment session recycler counter after successful analysis
        session_handler.increment()

        # Aggressive GPU memory cleanup after each MusiCNN analysis
        # This prevents gradual VRAM accumulation from ONNX Runtime allocator
        cleanup_cuda_memory(force=False)

        return analysis
    else:
        logger.info(f"SKIPPED MusiCNN for '{path}' (already analyzed)")
        return None

def analyze_files(file_paths: list, directory_name, session_handler:SessionHandler = None, handle_result_callback=None, force=False):
    # 2. Start the stopwatch
    start_time = time.perf_counter()

    logger.info(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Directory analysis task started.")

    tracks_analyzed_count, tracks_skipped_count = 0, 0

    PER_SONG_MODEL_RELOAD = False
    # Initialize SessionRecycler to prevent cumulative memory leaks
    # Interval depends on PER_SONG_MODEL_RELOAD setting:
    # - true: Reload every 1 song (aggressive, prevents memory leaks)
    # - false: Reload every 20 songs (original behavior, faster but may accumulate memory)

    cleanup_session = False
    if session_handler is None:
        session_handler = begin_session(PER_SONG_MODEL_RELOAD)
        cleanup_session = True

    try:
        if not file_paths:
            return {"status": "SUCCESS", "message": f"No tracks in directory {directory_name}", "tracks_analyzed": 0}

        total_tracks_in_album = len(file_paths)

        for idx, path in enumerate(file_paths, 1):
            result = analyze_file(path, session_handler=session_handler, force= force)

            if result is None:
                tracks_skipped_count += 1
            else:
                tracks_analyzed_count += 1

                if handle_result_callback:
                    handle_result_callback(path, result)

        summary = {"tracks_analyzed": tracks_analyzed_count, "tracks_skipped": tracks_skipped_count, "total_tracks_in_album": total_tracks_in_album}
        return {"status": "SUCCESS", **summary}

    except Exception as e:
        logger.critical(f"Analysis {directory_name} failed: {e}", exc_info=True)
        traceback.print_exc()
        raise
    finally:

        # --- THE CHECK ---
        active_providers = session_handler.onnx_sessions['Embedding_discogs'].get_providers()
        logger.info(f"Active Providers: {active_providers}")
        if 'CUDAExecutionProvider' in active_providers:
            logger.info("Victory! You are running on the GPU via CUDA.")
        elif 'DmlExecutionProvider' in active_providers:
            logger.info("Victory! You are running on the GPU via DirectML.")
        else:
            logger.info("Fallback occurred. You are running on the CPU.")
        # ✅ Always cleanup, even on error or early return
        if cleanup_session:
            end_session(session_handler)

        # 4. Stop and calculate
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        logger.info(f"Inference took: {duration_ms:.2f} ms")

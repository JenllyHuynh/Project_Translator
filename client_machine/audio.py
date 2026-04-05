"""
  audio.py - Thu âm bằng WASAPI Loopback (Máy Chính)

  Không cần driver ảo. PyAudioWPATCH dùng WASAPI Loopback
  API của Windows để "copy" âm thanh từ loa/tai nghe
  Người nghe vẫn nghe bình thường, không mất tiếng
"""

import io
import wave
import threading
import pyaudiowpatch as pyaudio
import numpy as np

# --- Cấu hình audio ---
CHUNK_DURATION_SEC = 3      # Gửi mỗi 3 giây 1 lần
SAMPLE_RATE = 16000         # Whisper cần 16kHz
CHANNELS = 1                # Mono
SAMPLE_WIDTH = 2            # 16-bit = 2 bytes
FORMAT = pyaudio.paInt16

_pa_instance = None


def get_loopback_device():
    """
    Tự động tìm thiết bị WASAPI Loopback (tai nghe/loa đang dùng).
    Trả về (device_index, device_info) hoặc raise nếu không tìm thấy.
    """
    global _pa_instance
    if _pa_instance is None:
        _pa_instance = pyaudio.PyAudio()

    pa = _pa_instance

    # Lấy thiết bị output mặc định hiện tại (cái đang phát âm thanh)
    try:
        default_out = pa.get_default_wasapi_loopback()
        return default_out["index"], default_out
    except Exception:
        pass

    # Fallback: Duyệt tất cả thiết bị, tìm loopback
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        # Thiết bị loopback thường có "Loopback" hoặc maxInputChannels > 0
        if info.get("isLoopbackDevice", False):
            return i, info

    raise RuntimeError(
        "Không tìm thấy thiết bị WASAPI Loopback!\n"
        "Hãy chắc chắn tai nghe/loa đang hoạt động và chọn đúng trong Windows Sound Settings."
    )


def list_loopback_devices() -> list[dict]:
    """
    Liệt kê tất cả thiết bị loopback có thể dùng.
    Dùng để debug hoặc cho người dùng chọn thủ công.
    """
    global _pa_instance
    if _pa_instance is None:
        _pa_instance = pyaudio.PyAudio()

    devices = []
    for i in range(_pa_instance.get_device_count()):
        info = _pa_instance.get_device_info_by_index(i)
        if info.get("isLoopbackDevice", False):
            devices.append({"index": i, "name": info["name"]})
    return devices


def numpy_to_wav_bytes(audio_np: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """
    Chuyển numpy array (int16) thành WAV bytes trong RAM.
    Không ghi file, truyền thẳng qua mạng.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_np.tobytes())
    return buf.getvalue()


class AudioCapture:
    """
    Thu âm liên tục từ WASAPI Loopback.
    Khi đủ CHUNK_DURATION_SEC giây thì gọi callback với WAV bytes.
    """

    def __init__(self, on_chunk_ready, device_index: int = None, chunk_sec: float = CHUNK_DURATION_SEC):
        """
        on_chunk_ready: callable(wav_bytes: bytes) - gọi khi có chunk audio mới
        device_index: None = tự động, hoặc truyền index cụ thể
        """
        self.on_chunk_ready = on_chunk_ready
        self.chunk_sec = chunk_sec
        self.device_index = device_index
        self._stream = None
        self._thread = None
        self._running = False
        self._buffer = []
        self._frames_per_chunk = int(SAMPLE_RATE * chunk_sec)

    def start(self):
        global _pa_instance
        if _pa_instance is None:
            _pa_instance = pyaudio.PyAudio()

        if self.device_index is None:
            self.device_index, dev_info = get_loopback_device()
            print(f"🎧 Đang dùng thiết bị: {dev_info['name']}")

        # PyAudioWPATCH có thể capture với sample rate gốc của thiết bị
        # nhưng chúng ta cần 16kHz cho Whisper -> sẽ resample sau
        dev_info = _pa_instance.get_device_info_by_index(self.device_index)
        native_rate = int(dev_info.get("defaultSampleRate", 44100))

        self._native_rate = native_rate
        self._frames_per_chunk_native = int(native_rate * self.chunk_sec)

        CHUNK_SIZE = 1024  # Số frames mỗi lần đọc (nhỏ = ít latency)

        self._stream = _pa_instance.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=native_rate,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=CHUNK_SIZE,
        )

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f" Bắt đầu thu âm ({native_rate}Hz, chunk {self.chunk_sec}s)...")

    def _capture_loop(self):
        frames_collected = 0
        chunk_frames = []

        while self._running:
            try:
                data = self._stream.read(1024, exception_on_overflow=False)
                chunk_frames.append(data)
                frames_collected += 1024

                if frames_collected >= self._frames_per_chunk_native:
                    # Gộp buffer thành numpy array
                    raw = b"".join(chunk_frames)
                    audio_np = np.frombuffer(raw, dtype=np.int16)

                    # Resample về 16kHz nếu cần
                    if self._native_rate != SAMPLE_RATE:
                        audio_np = self._resample(audio_np, self._native_rate, SAMPLE_RATE)

                    # Kiểm tra có tín hiệu không (tránh gửi im lặng)
                    rms = np.sqrt(np.mean(audio_np.astype(np.float32) ** 2))
                    if rms > 50:  # Ngưỡng im lặng (điều chỉnh nếu cần)
                        wav_bytes = numpy_to_wav_bytes(audio_np)
                        self.on_chunk_ready(wav_bytes)
                    else:
                        print(" Im lặng, bỏ qua chunk này")

                    # Reset buffer
                    chunk_frames = []
                    frames_collected = 0

            except Exception as e:
                if self._running:
                    print(f" Lỗi capture: {e}")

    @staticmethod
    def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
        """Resample đơn giản bằng numpy (không cần scipy)."""
        if orig_rate == target_rate:
            return audio
        ratio = target_rate / orig_rate
        target_len = int(len(audio) * ratio)
        indices = np.round(np.linspace(0, len(audio) - 1, target_len)).astype(int)
        return audio[indices]

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
        print(" Dừng thu âm.")


# Test nhanh khi chạy file này trực tiếp
if __name__ == "__main__":
    print("=== Test Audio Capture ===")
    print("Các thiết bị Loopback tìm thấy:")
    devices = list_loopback_devices()
    for d in devices:
        print(f"  [{d['index']}] {d['name']}")

    def on_chunk(wav_bytes):
        size_kb = len(wav_bytes) / 1024
        print(f" Chunk nhận được: {size_kb:.1f}KB - Gửi sang server!")

    capture = AudioCapture(on_chunk_ready=on_chunk)
    capture.start()

    input("\nNhấn Enter để dừng...\n")
    capture.stop()

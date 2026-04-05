"""
  network.py - Gửi audio sang máy phụ (Máy Chính)
"""

import requests
import threading
from typing import Callable

# ĐỔI IP NÀY thành IP của máy phụ
# CMD trên máy phụ -> ipconfig-> tìm "IPv4 Address"
SERVER_IP   = "192.168.1.100"   # <- ĐỔI IP NÀY
SERVER_PORT = 8000
SERVER_URL  = f"http://{SERVER_IP}:{SERVER_PORT}"
TIMEOUT_SEC = 15   # medium model chậm hơn small, tăng timeout lên 15s


def check_server_alive() -> bool:
    try:
        r = requests.get(f"{SERVER_URL}/health", timeout=3)
        if r.status_code == 200:
            data = r.json()
            print(f"  Whisper: {data.get('whisper_model')}  |  Dịch: {data.get('translation')}")
            return True
    except Exception:
        pass
    return False


def send_audio_chunk(wav_bytes: bytes) -> dict | None:
    """
    Gửi WAV bytes, nhận về:
    {
        "en": "Hello everyone...",
        "vi": "Xin chào mọi người...",
        "whisper_ms": 1200,
        "translate_ms": 310,
        "total_ms": 1510
    }
    """
    try:
        files    = {"audio": ("chunk.wav", wav_bytes, "audio/wav")}
        response = requests.post(
            f"{SERVER_URL}/transcribe",
            files=files,
            timeout=TIMEOUT_SEC,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print(f" Không kết nối {SERVER_URL}")
    except requests.exceptions.Timeout:
        print(f" Server timeout sau {TIMEOUT_SEC}s (medium model đang bận?)")
    except requests.exceptions.HTTPError as e:
        print(f" HTTP {e.response.status_code}: {e.response.text[:200]}")
    except Exception as e:
        print(f" Lỗi: {e}")
    return None


class AsyncSender:
    """
    Gửi audio trong background thread.
    on_result(en, vi, whisper_ms, translate_ms, total_ms)
    """

    def __init__(self, on_result: Callable[[str, str, int, int, int], None]):
        self.on_result = on_result
        self._pending  = False

    def send(self, wav_bytes: bytes):
        if self._pending:
            print(" Server đang xử lý, bỏ qua chunk này...")
            return
        threading.Thread(
            target=self._worker, args=(wav_bytes,), daemon=True
        ).start()

    def _worker(self, wav_bytes: bytes):
        self._pending = True
        try:
            result = send_audio_chunk(wav_bytes)
            if result:
                en  = result.get("en", "")
                vi  = result.get("vi", "")
                w   = result.get("whisper_ms", 0)
                t   = result.get("translate_ms", 0)
                tot = result.get("total_ms", 0)
                if en:   # chỉ callback khi có nội dung
                    self.on_result(en, vi, w, t, tot)
        finally:
            self._pending = False


if __name__ == "__main__":
    print(f"Kiểm tra {SERVER_URL}...")
    print(" OK!" if check_server_alive() else " Không kết nối được.")

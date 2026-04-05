"""
  PROJECT TRANSLATOR - CLIENT (Máy Chính 8GB RAM)

  Chạy: python main.py

  Luồng:
    GUI khởi động -> kiểm tra server -> AudioCapture
    -> gửi WAV 3s -> nhận {en, vi} -> hiển thị song ngữ
"""

import sys
import threading
import time

from audio   import AudioCapture, list_loopback_devices
from network import AsyncSender, check_server_alive, SERVER_URL
from gui     import TranslatorOverlay


def main():
    print("=" * 55)
    print("  PROJECT TRANSLATOR - CLIENT  (song ngữ EN/VI)")
    print("=" * 55)

    overlay = TranslatorOverlay()
    overlay.show_connecting()

    def connect_loop():
        retry = 0
        while True:
            print(f"\n Kiểm tra server {SERVER_URL}...")
            if check_server_alive():
                print(" Server OK!")
                overlay.set_status("● Server kết nối OK", "#34D399")
                time.sleep(0.5)
                start_capture()
                break
            retry += 1
            msg = f"Không kết nối ({retry}), thử lại sau 5s..."
            print(f" {msg}")
            overlay.show_error(msg)
            time.sleep(5)

    def start_capture():
        # Callback nhận kết quả song ngữ từ server
        def on_result(en: str, vi: str, whisper_ms: int, translate_ms: int, total_ms: int):
            print(f"\n🇬🇧 [{whisper_ms}ms] {en}")
            print(f"🇻🇳 [{translate_ms}ms] {vi}")
            overlay.show_transcript(en, vi, whisper_ms, translate_ms, total_ms)

        sender = AsyncSender(on_result=on_result)

        def on_audio_chunk(wav_bytes: bytes):
            overlay.set_status("● Đang nhận diện...", "#FBBF24")
            sender.send(wav_bytes)

        # Liệt kê thiết bị loopback
        devices = list_loopback_devices()
        if not devices:
            overlay.show_error("Không tìm thấy WASAPI Loopback!")
            print(" Không tìm thấy thiết bị WASAPI Loopback.")
            print(" Đảm bảo tai nghe/loa đang hoạt động.")
            return

        print(f"\n Loopback devices ({len(devices)}):")
        for d in devices:
            print(f"  [{d['index']}] {d['name']}")

        capture = AudioCapture(on_chunk_ready=on_audio_chunk)
        try:
            capture.start()
        except RuntimeError as e:
            overlay.show_error(str(e))
            print(f" {e}")

    threading.Thread(target=connect_loop, daemon=True).start()

    print("\n Overlay đang chạy. Đóng cửa sổ để thoát.\n")
    overlay.run()
    print("\n Đã thoát.")


if __name__ == "__main__":
    main()

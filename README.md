# Project Translator v1.0 - Song Ngữ EN/VI (Miễn Phí, Không API Key)

Real-time English transcript + Vietnamese translation overlay cho meetings.
**Không cần API key nào cả** - dùng Whisper medium + Google Translate unofficial.

---

##  Cấu Trúc

```
Project_Translator/
├── server_machine/        Copy sang máy phụ (16GB DDR5)
│   ├── main.py            FastAPI + Whisper medium + googletrans
│   └── requirements.txt
└── client_machine/        Giữ trên máy chính (8GB)
    ├── main.py
    ├── audio.py
    ├── network.py
    ├── gui.py
    └── requirements.txt
```

---

## Bước 1: Setup Máy Phụ (16GB RAM DDR5)

### 1.1 Cài thư viện
```bash
cd server_machine
pip install -r requirements.txt
```
> Lần đầu chạy, faster-whisper tải model medium ~769MB về máy - bình thường.

### 1.2 Tìm IP máy phụ
```cmd
ipconfig
# Tìm "IPv4 Address" trong phần Ethernet/WiFi đang kết nối LAN
# Ví dụ: 192.168.1.105
```

### 1.3 Mở port firewall
```powershell
# PowerShell với quyền Admin
New-NetFirewallRule -DisplayName "Translator Server" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

### 1.4 Chạy server
```bash
python main.py
```

Log bình thường:
```
 Loading Whisper 'medium' (~769MB, lần đầu sẽ tải về)...
 Whisper sẵn sàng!
 Google Translate client sẵn sàng!
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 1.5 Test (trình duyệt máy phụ)
`http://localhost:8000/health`
-> `{"status":"ok","whisper_model":"medium","translation":"googletrans (free, no key)"}`

---

## Bước 2: Setup Máy Chính (8GB RAM)

### 2.1 Cài thư viện
```bash
cd client_machine
pip install -r requirements.txt
```

### 2.2 ĐỔI IP SERVER
Mở `client_machine/network.py`, sửa:
```python
SERVER_IP = "192.168.1.105"   # <- IP máy phụ từ Bước 1.2
```

### 2.3 Chạy
```bash
python main.py
```

---

## Giao Diện Overlay

```
┌──────────────────────────────────────────────────────────────┐
│ Translator  ● Live  [🗣 1400ms  🇻🇳 230ms  ⏱ 1630ms]  ◐ ⌫ ✕   │
├──────────────────────────────────────────────────────────────┤
│ 🇬🇧  Hello everyone, let's begin the Q3 review meeting...     │ 
│ ──────────────────────────────────────────────────────────── │
│ 🇻🇳  Xin chào mọi người, hãy bắt đầu cuộc họp quý 3...        │
└──────────────────────────────────────────────────────────────┘
```

| Nút | Chức năng |
|-----|-----------|
| Kéo header | Di chuyển cửa sổ |
| `◐` | Đổi độ trong suốt |
| `⌫` | Xoá lịch sử text |
| `✕` | Đóng |

---

## Troubleshooting

**Dịch Việt không ra / rỗng**
- googletrans đôi khi bị rate-limit nếu dùng nhiều -> chờ 30s rồi thử lại
- Kiểm tra máy phụ có internet không (googletrans cần kết nối web)

**Không tìm thấy Loopback device**
```bash
python audio.py   # In ra danh sách thiết bị
```

**Server chậm**
- Medium model CPU mất 1.5–3s/chunk - hoàn toàn bình thường
- Giảm `CHUNK_DURATION_SEC = 2` trong `audio.py` nếu muốn kết quả đến nhanh hơn

**2 máy không kết nối**
1. Cùng WiFi/LAN chưa
2. Firewall đã mở chưa (Bước 1.3)
3. Test: browser máy chính -> `http://[IP_MAY_PHU]:8000/health`

---

## Hiệu Năng Ước Tính

| Bước | Thời gian |
|------|-----------|
| Whisper medium (3s audio) | ~1.5–3s |
| Google Translate | ~200–400ms |
| Network LAN | <10ms |
| **Tổng delay** | **~2–4s** |

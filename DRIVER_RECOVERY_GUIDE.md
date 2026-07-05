# Hướng dẫn phục hồi sau khi cài Driver Phantom

## Nếu máy tính bị đen màn hình

### 1. Vào Safe Mode
- **Tắt nóng**: Nhấn giữ nút nguồn cho đến khi máy tắt hẳn
- **Kích hoạt Recovery**: Bật máy → khi thấy logo → nhấn giữ nút nguồn tắt đột ngột
- **Lặp lại 3 lần** → Lần thứ 4 sẽ vào "Preparing Automatic Repair"

### 2. Gỡ Driver trong Safe Mode
- Chọn `Troubleshoot` → `Advanced options` → `Startup Settings` → `Restart`
- Nhấn phím `4` hoặc `F4` để vào Safe Mode
- Mở `Device Manager` (chuột phải nút Start)
- Tìm `Display adapters` → Gỡ driver lạ (tên Codex, Virtual Display, MttVDD)
- **Quan trọng**: Tích chọn "Delete the driver software for this device"
- Tìm `Monitors` → Gỡ Virtual Monitor nào lạ

### 3. Khôi phục Registry
- Nhấn `Windows + R` → gõ `msconfig`
- Tab `Services` → Tích "Hide all Microsoft services"
- Tìm và bỏ tích dịch vụ "Codex", "VirtualDisplay", "Skemi Phantom"

## Phòng ngừa trong tương lai

### Skemi đã vô hiệu hóa driver
- Driver setup đã bị **vô hiệu hóa hoàn toàn**
- Các endpoint `/api/local-computer/bootstrap` trả lỗi 410
- Giao diện không còn nút "Download Skemi Setup"

### Sử dụng Live Viewer an toàn
- **Live Viewer**: Chế độ xem desktop thật, không cần driver
- **An toàn tuyệt đối**: Không can thiệp vào hệ thống
- **Hiệu suất cao**: Sử dụng Windows Graphics Capture API

### Giải pháp thay thế (đang phát triển)
- Ứng dụng C# sử dụng Windows Graphics Capture
- WebRTC streaming an toàn
- Điều khiển từ xa không cần driver

## Liên hệ hỗ trợ
Nếu gặp vấn đề:
1. Không chạy lại file .cmd cũ
2. Vào Safe Mode theo hướng dẫn trên
3. Liên hệ đội ngũ phát triển

---
*Lần cập nhật: 02/05/2026 - Driver setup đã bị vô hiệu hóa vì lý do an toàn*
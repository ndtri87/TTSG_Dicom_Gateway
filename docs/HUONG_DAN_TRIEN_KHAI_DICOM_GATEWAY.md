# 📘 TÀI LIỆU HƯỚNG DẪN TRIỂN KHAI HỆ THỐNG TTSG DICOM GATEWAY
### (Phương Pháp Cài Đặt Bằng File Cài Đặt Chuyên Nghiệp 1-Click `Setup.exe`)

---

## 📌 MỤC LỤC
1. [Tổng Quan Triển Khai](#1-tổng-quan-triển-khai)
2. [Bước 1: Khảo Sát Thông Số PACS & RIS Từ Bệnh Viện](#bước-1-khảo-sát-thông-số-pacs--ris-từ-bệnh-viện)
3. [Bước 2: Cài Đặt 1-Click Bằng File `Setup.exe`](#bước-2-cài-đặt-1-click-bằng-file-setupexe)
4. [Bước 3: Cấu Hình IP PACS/RIS Trên Giao Diện Web](#bước-3-cấu-hình-ip-pacsris-trên-giao-diện-web)
5. [Bước 4: Kích Hoạt Bản Quyền Hệ Thống (Licensing)](#bước-4-kích-hoạt-bản-quyền-hệ-thống-licensing)
6. [Bước 5: Bàn Giao Cho Kỹ Thuật Viên / Bác Sĩ Tại Phòng Khám](#bước-5-bàn-giao-cho-kỹ-thuật-viên--bác-sĩ-tại-phòng-khám)
7. [Bước 6: Kiểm Thử Nghiệm Thu Hoàn Chỉnh](#bước-6-kiểm-thử-nghiệm-thu-hoàn-chỉnh)
8. [Bước 7: Cập Nhật Bản Vá Mới Hoặc Gỡ Cài Đặt](#bước-7-cập-nhật-bản-vá-mới-hoặc-gỡ-cài-đặt)

---

## 1. TỔNG QUAN TRIỂN KHAI

Bạn chỉ cần mang **1 file duy nhất** đến bệnh viện:
📦 **`TTSG_DicomGateway_Setup_v2.0.exe`** (Dung lượng ~18 MB).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    QUY TRÌNH TRIỂN KHAI 1-CLICK                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
 1. Nháy đúp file: [ TTSG_DicomGateway_Setup_v2.0.exe ]
    └─ Bấm: Next -> Next -> Install -> Finish (Mất 10 giây)
       ├─ Tự động cài vào C:\Program Files\TTSG DICOM Gateway
       ├─ Tự động tạo dịch vụ Windows Service chạy ngầm 24/7
       ├─ Tự động mở cổng tường lửa Windows (Firewall Port 5000 & 105)
       └─ Tự động tạo Icon đẹp mắt trên màn hình Desktop
                                       │
                                       ▼
 2. Web Control Panel tự động mở lên tại: http://localhost:5000
    └─ Điền IP PACS/RIS -> Bấm Test C-ECHO (Thành Công)
                                       │
                                       ▼
 3. Kích Hoạt Bản Quyền Thương Mại
    └─ Copy Hardware ID -> Nạp file license.key -> Hoàn tất nghiệm thu!
```

---

## BƯỚC 1: KHẢO SÁT THÔNG SỐ PACS & RIS TỪ BỆNH VIỆN

Trước khi cài đặt, gửi bảng này cho IT Bệnh viện điền:

| Hạng mục | Ý nghĩa | Ví dụ |
| :--- | :--- | :--- |
| **PACS Server IP** | Địa chỉ IP máy chủ PACS nhận ảnh | `192.168.6.213` |
| **PACS Port** | Cổng lắng nghe C-STORE của PACS | `6002` hoặc `104` |
| **PACS Called AE Title** | Tên định danh của PACS | `PACSTTSG` |
| **Gateway Calling AE Title** | Tên Gateway đã đăng ký với PACS | `DICOM_GATEWAY` |
| **RIS / Worklist IP** | Địa chỉ máy chủ Worklist HIS/RIS | `192.168.6.211` |
| **RIS Port & AE Title** | Cổng & Tên định danh của RIS | `6002` / `RISTTSG` |

> [!TIP]
> Nhắc IT Bệnh viện thêm 1 dòng vào danh sách thiết bị trên PACS Server:
> - **AE Title**: `DICOM_GATEWAY`
> - **IP**: IP máy tính cài Gateway (VD: `192.168.6.100`)

---

## BƯỚC 2: CÀI ĐẶT 1-CLICK BẰNG FILE `SETUP.EXE`

1. Nhấp đúp chuột vào file **`TTSG_DicomGateway_Setup_v2.0.exe`**.
2. Chọn thư mục cài đặt mặc định: `C:\Program Files\TTSG DICOM Gateway` $\rightarrow$ Bấm **Next**.
3. Tick chọn **"Create a desktop icon"** $\rightarrow$ Bấm **Next**.
4. Bấm **Install**:
   * Trình cài đặt sẽ giải nén toàn bộ mã máy nhị phân C/C++.
   * Tự động đăng ký dịch vụ chạy ngầm **Windows Service (`TTSG_DicomGateway`)** khởi động cùng Windows 24/7.
   * Tự động cấu hình mở cổng tường lửa Windows Firewall.
5. Bấm **Finish** $\rightarrow$ Trình duyệt Web sẽ tự động mở trang quản trị **`http://localhost:5000`**.

---

## BƯỚC 3: CẤU HÌNH IP PACS/RIS TRÊN GIAO DIỆN WEB

1. Trên màn hình Web vừa mở, đăng nhập tài khoản Quản trị:
   * **Tên đăng nhập**: `trind`
   * **Mật khẩu mặc định**: `admin123`
2. Chọn Tab **⚙️ Cấu Hình Pacs & Ris**:
   * Điền IP, Port, AE Title của PACS và RIS theo thông tin khảo sát ở Bước 1.
   * Bấm nút **"💾 Lưu Cấu Hình"**.
3. **Kiểm tra thông luồng**:
   * Bấm nút **"🔍 Test PACS"** $\rightarrow$ Nhận thông báo: `🟢 Kết nối PACS Thành Công`.
   * Bấm nút **"🔍 Test RIS"** $\rightarrow$ Nhận thông báo: `🟢 Kết nối RIS Thành Công`.

---

## BƯỚC 4: KÍCH HOẠT BẢN QUYỀN HỆ THỐNG (LICENSING)

1. Chọn Tab **🔑 Bản Quyền & Hệ Thống**.
2. Tại mục **Mã Định Danh Máy Tính (Hardware ID)**:
   * Bấm nút **`[📋 Sao Chép]`** để lấy mã máy (VD: `TTSG-6F6E-BCA7-82EA-C52B`).
3. Dùng công cụ `license_generator.py` trên máy của bạn để tạo file `license.key` cho khách hàng:
   ```powershell
   python license_generator.py --customer "Bệnh viện Đa khoa Tâm Trí Sài Gòn" --hwid "TTSG-6F6E-BCA7-82EA-C52B" --exp "2030-12-31" --modalities "US,ES,ECG,DR,CR,CT,MR" --stations 50 --out "license.key"
   ```
4. Trên Web của khách hàng: Chọn file `license.key` $\rightarrow$ Bấm **"🔑 Kích Hoạt Bản Quyền Ngay"**.
5. Màn hình báo: **🟢 Bản Quyền Hợp Lệ (Enterprise Edition)**.

---

## BƯỚC 5: BÀN GIAO CHO KỸ THUẬT VIÊN / BÁC SĨ TẠI PHÒNG KHÁM

Tại các máy tính của phòng khám (Siêu âm, Nội soi, Điện tim):

1. Mở trình duyệt Chrome/Edge truy cập: `http://192.168.0.3:5000` *(IP của máy chủ Gateway)*.
2. Tạo lối tắt (Shortcut) ra màn hình Desktop: **`PACS Gateway - Phòng Siêu Âm`**.
3. **Trải nghiệm 1-chạm của Kỹ thuật viên**:
   * Mở ứng dụng $\rightarrow$ Nhấp chọn đúng phòng của mình (VD: *🩺 Phòng Siêu âm 01*).
   * Tick chọn **"Ghi nhớ nơi làm việc trên máy này"**.
   * Bấm **"🚀 Vào Làm Việc Ngay"** (Không cần gõ mật khẩu).
   * Giao diện hiển thị danh sách bệnh nhân chờ khám từ Worklist.
   * KTV chọn bệnh nhân $\rightarrow$ Kéo ảnh JPG/PDF vào $\rightarrow$ Bấm **"🚀 Đẩy PACS"** là xong!

---

## BƯỚC 6: KIỂM THỬ NGHIỆM THU HOÀN CHỈNH

Kỹ sư triển khai cùng IT Bệnh viện kiểm tra:
- [x] **Test C-ECHO PACS & RIS**: Cả 2 đều báo Thành Công.
- [x] **Truy vấn Worklist**: Tìm kiếm ngày hôm nay hiển thị đúng danh sách chỉ định.
- [x] **Gửi ca thực tế**: Gửi 1 ca siêu âm kèm ảnh $\rightarrow$ Mở phần mềm xem ảnh PACS Viewer của Bệnh viện xác nhận đã có hình ảnh.
- [x] **Khởi động lại máy chủ**: Restart lại máy Gateway $\rightarrow$ Mở máy trạm kiểm tra dịch vụ vẫn tự động hoạt động bình thường.

---

## BƯỚC 7: CẬP NHẬT BẢN VÁ MỚI HOẶC GỠ CÀI ĐẶT

### 1. Nâng Cấp Phiên Bản Mới (.pkg)
* Khi có bản nâng cấp tính năng: Gửi file `TTSG_Gateway_Patch_vX.X.X.pkg`.
* Khách vào Web $\rightarrow$ Tab *Bản Quyền & Hệ Thống* $\rightarrow$ Chọn file `.pkg` $\rightarrow$ Bấm **"🚀 Cập Nhật Ngay"** (Cập nhật xong trong 3 giây, giữ nguyên CSDL và cấu hình).

### 2. Gỡ Cài Đặt Sạch Sẽ (Uninstall)
* Vào **Windows Settings $\rightarrow$ Installed Apps** (hoặc `Control Panel \ Programs`).
* Chọn **`TTSG DICOM Gateway`** $\rightarrow$ Bấm **Uninstall**.
* Hệ thống sẽ tự động dừng Windows Service, xóa dịch vụ và dọn dẹp sạch sẽ toàn bộ hệ thống.

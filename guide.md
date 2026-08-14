# Hướng Dẫn Setup & Vận Hành Chi Tiết DICOM Gateway (Client - Server Architecture)

Tài liệu này hướng dẫn chi tiết từ A-Z cách thiết lập, cấu hình và vận hành hệ thống **DICOM Gateway Service** theo mô hình **Client - Server chuyên nghiệp**, cách ly tuyệt đối giữa mạng bệnh viện (`10.4.140.x`) và mạng PACS/RIS nội bộ (`192.168.6.x`).

---

## 🏗️ 1. Tổng Quan Kiến Trúc Mạng & Địa Chỉ IP

```
[MẠNG PHÒNG KHÁM BỆNH VIỆN - VLAN 10.4.140.x]
┌────────────────────────────────────────────────────────────┐
│ Máy Trạm Siêu Âm / Điện Tim / Nội Soi / Đo Hô Hấp         │
│ - Cài đặt Client Agent (client_agent.exe / client_config)  │
│ - Tự động quét ảnh/PDF từ C:\ExportImage                   │
└──────────────────────────────┬─────────────────────────────┘
                               │ HTTP REST API (Port 5000)
                               ▼
[GATEWAY SERVER TRUNG TÂM - IP: 192.168.0.3 / Dual-NIC]
┌────────────────────────────────────────────────────────────┐
│ NIC 1 (VLAN Bệnh Viện): 192.168.0.3 (Nhận dữ liệu Client)  │
│ Engine Core: Flask API (Port 5000), DICOM Builder, SQLite  │
│ NIC 2 (VLAN PACS/RIS): 192.168.6.200 (Giao tiếp y tế)      │
└──────────────┬──────────────────────────────┬──────────────┘
               │ DICOM C-FIND                 │ DICOM C-STORE
               ▼                              ▼
┌──────────────────────────────┐┌─────────────────────────────┐
│ RIS Server (192.168.6.211)   ││ PACS Server (192.168.6.213)│
└──────────────────────────────┘└─────────────────────────────┘
[MẠNG PACS / RIS NỘI BỘ - VLAN 192.168.6.x]
```

---

## 🖥️ 2. Hướng Dẫn Setup Tại GATEWAY SERVER TRUNG TÂM (`192.168.0.3`)

### Bước 2.1: Cấu hình Mạng & Tường Lửa (Dual-NIC Setup)
1. **Cấu hình 2 Card Mạng trên Server**:
   * **Card 1 (NIC 1)**: Nối vào mạng bệnh viện (`192.168.0.3`). Điền Subnet Mask & Default Gateway mạng bệnh viện.
   * **Card 2 (NIC 2)**: Nối vào mạng PACS/RIS (`192.168.6.200`). Điền Subnet Mask, **KHÔNG điền Default Gateway** (tránh đụng độ định tuyến mạng).
2. **Cấu hình Windows Firewall Rule**:
   * Mở Inbound **Port 5000 (TCP)** cho phép tất cả các máy phòng khám kết nối về Server.

### Bước 2.2: Cài Đặt & Khởi Chạy Server
1. Copy/Giải nén thư mục mã nguồn `nonDicom` vào Server (Ví dụ: `C:\DICOM_Gateway\nonDicom`).
2. Double-click file **`setup.bat`**: Script sẽ tự tạo môi trường ảo Python `.venv` và cài đặt tự động đầy đủ thư viện.
3. Mở file **`config.yaml`** để cấu hình thông số kết nối PACS/RIS:
   ```yaml
   pacs:
     ip: "192.168.6.213"
     port: 6002
     called_ae_title: "PACSTTSG"
     calling_ae_title: "DICOM_GATEWAY"
   ris:
     enabled: true
     ip: "192.168.6.211"
     port: 6002
     called_ae_title: "RISTTSG"
     calling_ae_title: "DICOM_GATEWAY"
   ```
4. Kiểm tra kết nối PACS C-ECHO: Double-click **`test_ket_noi_pacs.bat`** ➔ Kết quả báo `[THANH CONG]`.
5. Khởi chạy Server chính: Double-click **`run.bat`** (Khởi chạy service background trên Port 5000).

---

## 💻 3. Hướng Dẫn Setup Tại MÁY TRẠM PHÒNG KHÁM (CLIENT - `10.4.140.x`)

Client Agent hiện tại đã chuyển sang **file cài đặt / thực thi độc lập (`client_agent.exe`)**, **KHÔNG cần cài đặt Python** hay bất kỳ môi trường/thư viện nào trên máy trạm thiết bị y tế.

### Bước 3.1: Đóng Gói / Lấy File Cài Đặt Client Exe
* **Đối với người triển khai (Dev/Admin)**: Nếu cần tự đóng gói từ mã nguồn thành file `.exe` độc lập mới nhất, chạy file **`build_client_exe.bat`**. Kết quả file thực thi sẽ nằm tại: `dist\client_agent.exe`.
* **Đối với máy trạm Client**: Chỉ cần lấy file `client_agent.exe` đã đóng gói sẵn trong thư mục `dist\` hoặc bộ cài Client.

### Bước 3.2: Copy File Cài Đặt Sang Máy Trạm
Tạo thư mục làm việc trên máy trạm phòng khám (Ví dụ: `C:\DICOM_Client`) và copy các file sau vào:
* **`client_agent.exe`** (File chạy chính độc lập)
* **`client_config.yaml`** (File cấu hình thông số Client)
* **`run_client.bat`** *(Tùy chọn: Script hỗ trợ tự động tìm và khởi chạy file exe hoặc script Python)*

### Bước 3.3: Cấu Hình `client_config.yaml`
Mở file `client_config.yaml` bằng Notepad và kiểm tra/chỉnh sửa các thông số:
```yaml
# Địa chỉ Gateway Server trung tâm
server_url: "http://192.168.0.3:5000"

# Thư mục thiết bị y tế xuất ảnh/PDF ra
watch_folder: "C:/ExportImage"

# Thư mục sao lưu file đã gửi thành công / thất bại
sent_folder: "./export/sent"
failed_folder: "./export/failed"
```

### Bước 3.4: Khởi Chạy & Cấu Hình Khởi Động Cùng Windows
1. **Khởi chạy thủ công**: Double-click **`client_agent.exe`** (hoặc **`run_client.bat`**).
   * Màn hình Console sẽ hiển thị thông báo đã nạp file cấu hình và bắt đầu theo dõi thư mục `C:\ExportImage`.
   * Khi thiết bị y tế xuất ảnh/PDF vào thư mục này, Client Agent sẽ tự động đẩy dữ liệu về Gateway Server `192.168.0.3`.
2. **Cấu hình tự động chạy khi bật máy (Windows Startup)**:
   * Nhấn tổ hợp phím **`Win + R`**, nhập **`shell:startup`** và nhấn **Enter** để mở thư mục Startup.
   * Kéo thả hoặc tạo Shortcut (Lối tắt) cho file `client_agent.exe` (hoặc `run_client.bat`) vào thư mục này.
   * Mỗi khi máy trạm phòng khám khởi động, Client Agent sẽ tự động chạy background.

> 💡 **Ghi chú (Tùy chọn chạy bằng Python Script gốc)**: Nếu máy trạm đã có sẵn Python và muốn chạy dưới dạng script `.py`, chỉ cần chạy `setup_client.bat` để tạo môi trường ảo `.venv_client` rồi thực thi `run_client.bat`.

---

## 🩺 4. Hướng Dẫn Vận Hành Web Dashboard (`http://192.168.0.3:5000`)

Bác sĩ hoặc Kỹ thuật viên mở trình duyệt bất kỳ tại máy phòng khám và gõ: **`http://192.168.0.3:5000`**

### 📋 Quy Trình Tra Cứu Worklist & Đẩy PACS Thuận Tiện:
1. **Bước 1: Tra cứu RIS Worklist**:
   * Mở tab **`📋 RIS Worklist`**.
   * Chọn Ngày chỉ định và Modality (X-quang `CR`, Nội soi `ES`, Hô hấp `PFT`, Siêu âm `US`...).
   * Bấm **`🔍 Load Worklist từ RIS`** (Thanh tìm kiếm gom gọn trên 1 dòng siêu tiết kiệm diện tích).
2. **Bước 2: Chọn Ca Khám**:
   * Nhấn nút **`🩺 Thực hiện CLS`** tại hàng bệnh nhân tương ứng. Hệ thống tự động chuyển sang Tab 3 và nạp 100% thông tin bệnh nhân (Mã BN, Họ tên, Số CĐ, Dịch vụ).
3. **Bước 3: Đính kèm File Kết Quả & Chọn Report Chính**:
   * Kéo thả một hoặc nhiều file PDF/Ảnh kết quả vào ô **Bước 3**.
   * **Đánh dấu File Report chính**: Danh sách file preview hiển thị nút chọn **`⭐ [Report chính]`** (nổi bật khung xanh lá). Mặc định chọn file đầu tiên làm Phiếu kết quả chính, các file còn lại đánh dấu là `📄 [File phụ]`.
4. **Bước 4: Đẩy PACS**:
   * Bấm **`🚀 Đẩy Lên PACS Ngay`**.
   * Trên phần mềm PACS: Cột **Report** của ca khám lập tức hiển thị phiếu kết quả PDF chuẩn DICOM (`InstanceNumber = 1`, `DocumentTitle = PHIẾU KẾT QUẢ CẬN LÂM SÀNG`).

---

## 🏷️ 5. Bảng Chuẩn Hóa Loại Thiết Bị (Modality Mapping)

| Mã Modality | Loại Thiết Bị Y Tế | Tên Dịch Vụ Mẫu Hệ Thống |
| :---: | :--- | :--- |
| **`CR`** | X-quang kỹ thuật số (Computed Radiography) | X-quang ngực thẳng |
| **`DX`** | X-quang số trực tiếp (Digital Radiography) | X-quang xương khớp |
| **`ES`** | Nội soi (Endoscopy) | Nội soi dạ dày / Đại tràng |
| **`PFT`** | Đo chức năng hô hấp (Pulmonary Function Test) | Đo dung tích phổi / Phế dung kế |
| **`US`** | Siêu âm (Ultrasound) | Siêu âm ổ bụng / Siêu âm tim |
| **`ECG`** | Điện tâm đồ (Electrocardiogram) | Điện tâm đồ thường |
| **`BD`** | Đo mật độ xương (Bone Density) | Đo loãng xương DEXA |
| **`DOC`** | Tài liệu / Báo cáo PDF | Báo cáo kết quả PDF |
| **`OT`** | Khác (Other) | Dịch vụ cận lâm sàng khác |

---

## 🛠️ 6. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| **Client báo `Không kết nối được Gateway Server`** | Tường lửa Server chặn hoặc sai IP `server_url` | 1. Đảm bảo máy trạm ping được `192.168.0.3`<br>2. Kiểm tra lại địa chỉ `server_url` trong `client_config.yaml`<br>3. Kiểm tra Inbound Port 5000 trong Windows Firewall trên Server. |
| **Client báo `Không tìm thấy client_config.yaml`** | Đặt file `client_agent.exe` sai thư mục | Đảm bảo file `client_config.yaml` nằm chung thư mục với `client_agent.exe`. |
| **Client Agent tắt khi tắt cửa sổ Command** | Đang chạy giao diện console | Tạo Shortcut của `client_agent.exe` (hoặc `run_client.bat`) thả vào `shell:startup` để tự khởi động cùng Windows. |
| **Server báo `Lỗi C-STORE đẩy PACS`** | PACS đổi IP, Port hoặc chặn AE Title | Double-click `test_ket_noi_pacs.bat` trên Server để test C-ECHO. Đảm bảo PACS chấp nhận Calling AE Title `DICOM_GATEWAY`. |
| **Tên Bệnh Nhân bị dính ký tự `^`** | Dữ liệu gốc từ RIS chứa ký tự phân cách | Gateway đã tích hợp tự động chuẩn hóa loại bỏ toàn bộ dấu `^` thành khoảng trắng. |
| **PACS không xếp file Report lên đầu** | PACS xếp theo InstanceNumber | Gateway tự động gán `InstanceNumber = 1` cho file Report chính và `2, 3...` cho các file phụ đính kèm. |


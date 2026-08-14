# PRD - Yêu Cầu Sản Phẩm & Kiến Trúc Hệ Thống DICOM Gateway Service (Non-DICOM Converter)

## 📌 1. TỔNG QUAN SẢN PHẨM (EXECUTIVE SUMMARY)

**Hệ thống DICOM Gateway Service** là giải pháp phần mềm trung gian (Middleware Gateway) chuyên dụng cho các môi trường Y Tế / Bệnh viện. Hệ thống giúp thu thập, chuẩn hóa và đóng gói tất cả các định dạng hình ảnh (.png, .jpg, .jpeg) và tài liệu kết quả (.pdf) từ các thiết bị y tế **không có chuẩn DICOM gốc** (Siêu âm, Nội soi, X-quang kỹ thuật số, Đo chức năng hô hấp, Điện tâm đồ, Đo mật độ xương...) thành dữ liệu **DICOM Chuẩn Quốc Tế** và đẩy trực tiếp vào hệ thống lưu trữ hình ảnh y tế **PACS** (Picture Archiving and Communication System) thông qua giao thức `DICOM C-STORE`.

Hệ thống đồng thời tích hợp trực tiếp với **RIS Modality Worklist (MWL)** qua giao thức `DICOM C-FIND` để tra cứu thông tin ca khám bệnh nhân tự động, triệt tiêu hoàn toàn việc gõ tay thông tin bệnh nhân, tránh nhầm lẫn dữ liệu y tế.

---

## 🏗️ 2. MÔ HÌNH KIẾN TRÚC HỆ THỐNG (SYSTEM ARCHITECTURE)

Hệ thống vận hành theo kiến trúc **Client - Server Phân Tách**, đáp ứng tiêu chuẩn an ninh mạng y tế với thiết lập Card mạng kép (Dual-NIC Network Isolation):

```
                                  [ MẠNG TOÀN BỆNH VIỆN - VLAN 10.4.140.x ]
                                                      │
             ┌────────────────────────────────────────┼────────────────────────────────────────┐
             │                                        │                                        │
             ▼                                        ▼                                        ▼
   ┌──────────────────┐                     ┌──────────────────┐                     ┌──────────────────┐
   │ Máy Trạm P.Khám  │                     │ Máy Trạm P.Khám  │                     │ Trình Duyệt Web  │
   │   (Phòng Siêu Âm) │                     │  (Phòng Nội Soi) │                     │ (Bác Sĩ/KTV)     │
   │  Client Agent    │                     │  Client Agent    │                     │  Web Dashboard   │
   └─────────┬────────┘                     └─────────┬────────┘                     └─────────┬────────┘
             │ HTTP Upload (Port 5000)                │ HTTP Upload (Port 5000)                │ HTTP (Port 5000)
             └────────────────────────────────────────┼────────────────────────────────────────┘
                                                      │
                                                      ▼
                            ┌──────────────────────────────────────────────────┐
                            │ GATEWAY SERVER TRUNG TÂM (IP: 192.168.0.3)      │
                            │ ----------------───────────────────────────────  │
                            │ NIC 1: 192.168.0.3 (Nhận dữ liệu từ Client)      │
                            │ Engine Core: Flask Web API, DICOM Engine,        │
                            │              SQLite Queue DB, Worklist Client    │
                            │ NIC 2: 192.168.6.200 (Giao tiếp PACS/RIS)        │
                            └─────────────────────────┬────────────────────────┘
                                                      │
                                   ┌──────────────────┴──────────────────┐
                                   │ DICOM C-FIND                        │ DICOM C-STORE
                                   ▼                                     ▼
                        ┌─────────────────────┐               ┌─────────────────────┐
                        │ RIS WORKLIST SERVER │               │ PACS CENTRAL SERVER │
                        │  (192.168.6.211)    │               │  (192.168.6.213)    │
                        └─────────────────────┘               └─────────────────────┘
                                   [ MẠNG PACS / RIS NỘI BỘ - VLAN 192.168.6.x ]
```

### 2.1. Gateway Server Trung Tâm (`192.168.0.3`)
* **Chức năng**:
  * Cung cấp RESTful API & Web Dashboard quản trị điều khiển trên Port `5000`.
  * Đóng vai trò là cầu nối mạng kép (Dual-NIC Bridge): Tiếp nhận yêu cầu từ VLAN Bệnh viện (`10.4.140.x`) trên NIC 1 (`192.168.0.3`) và truyền DICOM tới PACS/RIS trên NIC 2 (`192.168.6.200`).
  * Thực hiện đóng gói ảnh/PDF sang chuẩn DICOM (Secondary Capture Image / Encapsulated PDF).
  * Tra cứu RIS Worklist qua C-FIND.
  * Đẩy dữ liệu DICOM sang PACS Server qua C-STORE với cơ chế tự động thử lại (Retry Queue & Offline Buffer).
* **Yêu cầu môi trường**: Python 3.10+, `pydicom`, `pynetdicom`, `flask`, `watchdog`, `pyyaml`, `pillow`, `requests`.

### 2.2. Client Agent tại Máy Trạm Phòng Khám (`client_agent.py`)
* **Chức năng**:
  * Chạy dưới dạng service/background process siêu nhẹ tại các máy trạm thiết bị y tế (VLAN `10.4.140.x`).
  * Quét tự động (Auto-watch) thư mục xuất ảnh local của thiết bị (VD: `C:\ExportImage`).
  * Tự động gửi file ngầm qua HTTP REST API về Gateway Server `http://192.168.0.3:5000`.
  * Hỗ trợ bộ đệm ngoại tuyến (Offline Buffer): Khi mất kết nối mạng với Gateway Server, Client giữ lại file trong ổ đĩa local (`./export/sent`, `./export/failed`) và tự động gửi bù ngay khi có mạng trở lại.
* **Yêu cầu môi trường**: Python 3.10+ siêu nhẹ, chỉ cần `requests` và `pyyaml` (không cần cài các thư viện DICOM nặng).

---

## 📋 3. DANH SÁCH MÃ MODALITY MẪU CỦA HỆ THỐNG

Hệ thống đã chuẩn hóa bảng phân loại loại thiết bị (Modality) tương thích chuẩn y tế quốc tế DICOM:

| Modality Code | Tên Tiếng Việt Chuẩn | Tên Tiếng Anh Chuẩn (DICOM Standard) | Ứng Dụng Thiết Bị |
| :---: | :--- | :--- | :--- |
| **`CR`** | X-quang kỹ thuật số | Computed Radiography | Máy X-quang chụp rửa phim kỹ thuật số |
| **`DX`** | X-quang số trực tiếp | Digital Radiography | Máy X-quang tấm thu kỹ thuật số |
| **`ES`** | Nội soi | Endoscopy | Máy nội soi tiêu hóa, dạ dày, tai mũi họng |
| **`PFT`** | Đo chức năng hô hấp | Pulmonary Function Test | Máy đo dung tích phổi, phế dung kế |
| **`US`** | Siêu âm | Ultrasound | Máy siêu âm 2D/3D/4D, siêu âm tim, ổ bụng |
| **`ECG`** | Điện tâm đồ | Electrocardiogram | Máy đo điện tim |
| **`BD`** | Đo mật độ xương | Bone Density / DEXA | Máy đo loãng xương |
| **`DOC`** | Tài liệu / Báo cáo PDF | Document | File báo cáo kết quả PDF |
| **`OT`** | Khác | Other | Các thiết bị cận lâm sàng khác |

---

## 📄 4. CHUẨN ĐÓNG GÓI DICOM & HIỂN THỊ KẾT QUẢ (REPORT) TRÊN PACS

### 4.1. Quy chuẩn SOP Class DICOM
* **Tài liệu PDF kết quả**: Đóng gói theo chuẩn **`DICOM Encapsulated PDF`** (`SOP Class UID: 1.2.840.10008.5.1.4.1.1.104.1`).
* **File Hình Ảnh (.png, .jpg, .jpeg)**: Đóng gói theo chuẩn **`DICOM Secondary Capture Image`** (`SOP Class UID: 1.2.840.10008.5.1.4.1.1.7`).

### 4.2. Cơ chế kích hoạt cột Report & Xem Báo Cáo trên PACS
Khi Gateway đẩy dữ liệu vào PACS, PACS sẽ lập tức kích hoạt biểu tượng **Report (Kết quả)** của ca khám đó nhờ các thẻ DICOM Metadata được ghi nhận:

1. **Phân định File Report chính vs File phụ đính kèm**:
   * Khi tải lên nhiều file cùng lúc trên Web Dashboard, người dùng chọn nút Radio **`⭐ [Report chính]`** cho file kết quả chính.
2. **Cấu trúc thẻ DICOM Metadata**:

| Thẻ DICOM Tag | File Phiếu Kết Quả Chính (Main Report) | Các File Ảnh / Tài Liệu Phụ |
| :--- | :--- | :--- |
| **`(0020,0013) InstanceNumber`** | **`1`** *(Ưu tiên xếp vị trí #1 trên PACS)* | `2`, `3`, `4`... |
| **`(0042,0010) DocumentTitle`** | **`PHIẾU KẾT QUẢ CẬN LÂM SÀNG`** | `Tài liệu đính kèm ([Tên file])` |
| **`(0008,103E) SeriesDescription`** | **`Diagnostic Report`** | `Attachment` |
| **`(0010,0010) PatientName`** | Chuẩn hóa xóa sạch kí tự dính `^` | Chuẩn hóa xóa sạch kí tự dính `^` |

---

## 💻 5. GIAO DIỆN NGUYÊN KHỐI WEB DASHBOARD (`index.html`)

Giao diện Web Control Panel tích hợp 4 Tab quản trị tập trung:

1. **Tab 1: 📊 Tổng Quan & Trạng Thái Hệ Thống**:
   * Theo dõi realtime số lượng ca đẩy thành công, hàng đợi thử lại, log terminal trực tiếp.
2. **Tab 2: 📋 RIS Worklist**:
   * **Thanh tìm kiếm siêu gọn (Single-line Compact Filter Bar)**: Ngày chỉ định, Mã BN, Họ tên, Modality (`CR`, `ES`, `PFT`, `US`...) gom gọn trên 1 dòng duy nhất.
   * Danh sách bệnh nhân chờ chụp từ RIS. Bấm **`🩺 Thực hiện CLS`** sẽ nạp tự động thông tin sang Tab 3.
3. **Tab 3: 📤 Nhập Ca Khám Thủ Công & Đẩy PACS**:
   * **Bước 3: Đính kèm kết quả**: Cho phép kéo thả nhiều file PDF/Ảnh.
   * Hiển thị danh sách file với Radio Button **`⭐ [Report chính]`** nổi bật viền xanh lá.
   * Bổ sung menu chọn nhanh **Dịch vụ mẫu** (Siêu âm, Điện tim, X-quang, Nội soi, Đo hô hấp, Loãng xương...).
4. **Tab 4: 📜 Lịch Sử Ca Khám & Cấu Hình Kết Nối**:
   * Tra cứu lịch sử đẩy ca khám, thử lại ca lỗi, thử kết nối C-ECHO PACS/RIS.

---

## 🔒 6. NGUYÊN TẮC AN NINH & VẬN HÀNH BỀN VỮNG

1. **Cách ly mạng tuyệt đối (Air-Gap Protection)**: Các máy trạm phòng khám `10.4.140.x` không thể truy cập trực tiếp vào hệ thống PACS/RIS `192.168.6.x`. Mọi luồng dữ liệu bắt buộc đi qua Gateway Server kiểm duyệt.
2. **Không mất mát dữ liệu (Zero Data Loss Guarantee)**: Hệ thống duy trì cơ chế Retry Queue (SQLite DB) tại Server và Offline File Buffer tại Client. Khi sự cố mạng hoặc PACS downtime xảy ra, dữ liệu tự động gửi lại ngay khi hệ thống phục hồi.
3. **Chuẩn hóa Tên Bệnh Nhân (Patient Name Sanitization)**: Tự động lọc toàn bộ ký tự phân cách dấu `^` trong DICOM thành khoảng trắng để hiển thị trên phần mềm PACS đẹp mắt, chuẩn Unicode UTF-8 (`ISO_IR 192`).

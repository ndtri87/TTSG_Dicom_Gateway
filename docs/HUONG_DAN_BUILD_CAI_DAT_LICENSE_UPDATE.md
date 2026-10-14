# HƯỚNG DẪN BUILD → CÀI ĐẶT → CẤP LICENSE → CẬP NHẬT
### TTSG DICOM Gateway — tài liệu vận hành chuẩn (thay thế các phần tương ứng trong các tài liệu cũ)

> **Dành cho:** Nhà phát triển (build, ký license, đóng bản vá) và Kỹ sư triển khai / IT bệnh viện (cài đặt, kích hoạt, cập nhật).
> Mỗi bước ghi rõ **ai làm** và **làm ở máy nào**.

---

## MỤC LỤC
1. [Tổng quan quy trình](#1-tổng-quan-quy-trình)
2. [Chuẩn bị máy phát triển (làm 1 lần)](#2-chuẩn-bị-máy-phát-triển-làm-1-lần)
3. [Build bộ cài](#3-build-bộ-cài)
4. [Cài đặt Gateway Server tại bệnh viện](#4-cài-đặt-gateway-server-tại-bệnh-viện)
5. [Cài đặt máy trạm (Client Agent)](#5-cài-đặt-máy-trạm-client-agent)
6. [Cấp & kích hoạt license](#6-cấp--kích-hoạt-license)
7. [Cập nhật phiên bản](#7-cập-nhật-phiên-bản)
8. [Đổi máy chủ / đổi IP / đổi port](#8-đổi-máy-chủ--đổi-ip--đổi-port)
9. [Vận hành & xử lý sự cố](#9-vận-hành--xử-lý-sự-cố)
10. [Phụ lục: vị trí file & checklist bảo mật](#10-phụ-lục-vị-trí-file--checklist-bảo-mật)

---

## 1. TỔNG QUAN QUY TRÌNH

```
 MÁY PHÁT TRIỂN                                   MÁY CHỦ GATEWAY (BỆNH VIỆN)               MÁY TRẠM PHÒNG KHÁM
 ─────────────────                                ───────────────────────────               ───────────────────
 [2] setup.bat (1 lần)
 [3] build_setup_installer.bat ──Setup.exe──────► [4] Cài Setup.exe
     Client\build_client_exe.bat ──TTSG_ClientAgent──────────────────────────────────────► [5] Chép + cấu hình
                                                       Lấy Hardware ID
 [6] tao_license.bat ◄────────── Hardware ID ─────────┘
                      ──────── license.key ─────► [6] Kích hoạt trên Web
 [7] build_server_exe + build_patch ──.pkg──────► [7] Cập nhật trên Web
```

| Thành phần | Mô tả |
|---|---|
| **Gateway Server** | Windows Service `TTSG_DicomGateway`, Web quản trị cổng **5000**, nhận Storage Commitment cổng **105** |
| **Client Agent** | Chương trình nhỏ trên máy trạm: theo dõi thư mục xuất ảnh của máy y tế và tự gửi về Gateway |
| **License** | File `license.key` ký số RSA, khóa theo **Hardware ID** máy chủ; chưa có license → dùng thử 30 ngày |
| **Bản vá `.pkg`** | Gói cập nhật có chữ ký số, nạp qua Web, **không đụng** cấu hình / dữ liệu / license |

---

## 2. CHUẨN BỊ MÁY PHÁT TRIỂN (LÀM 1 LẦN)

👤 **Nhà phát triển** · 💻 **Máy phát triển**

1. Cài **Python 3.10+** — khi cài tick ☑ *Add Python to PATH*.
2. Cài **Inno Setup 6** (https://jrsoftware.org/isdl.php).
3. Nhấp đúp **`setup.bat`** → tạo môi trường `.venv`, cài thư viện, và tạo **`config.yaml`** từ mẫu `config.default.yaml` nếu chưa có. Thấy `=== Cai dat xong ===` là xong.
   - `config.yaml` là cấu hình **riêng của từng máy** (mật khẩu, IP nội bộ, mã Client Agent) → đã bị `.gitignore`, **không commit**. Muốn đổi cấu hình mặc định cho mọi site thì sửa `config.default.yaml`.
4. **Khóa ký bản quyền** — file `keys\license_private.pem`:
   - Dùng để ký **license** và **bản vá**. Không có file này thì không cấp được license mới.
   - **SAO LƯU NGAY** ra USB mã hóa / kho mật khẩu của công ty.
   - **TUYỆT ĐỐI KHÔNG** commit lên Git, gửi qua Zalo/Email, hay chép sang máy khách hàng (thư mục `keys/` đã bị `.gitignore`).
   - Muốn để khóa ở chỗ khác: đặt biến môi trường `TTSG_LICENSE_PRIVATE_KEY=<đường dẫn file .pem>`.

> ⚠️ Cặp khóa đã được **thay mới ngày 14/10/2026** (khóa cũ bị lộ). License và bản vá ký bằng khóa cũ **không còn hợp lệ** với các bản build từ ngày này — xem [mục 7.3](#73-lần-nâng-cấp-đầu-tiên-sau-khi-đổi-khóa-bắt-buộc-làm).

---

## 3. BUILD BỘ CÀI

👤 **Nhà phát triển** · 💻 **Máy phát triển**

### 3.1. Đặt số phiên bản
Mở [`installer.iss`](../installer.iss), sửa 2 dòng:
```
#define MyAppVersion "2.1.0"
OutputBaseFilename=TTSG_DicomGateway_Setup_v2.1
```

### 3.2. Kiểm tra cấu hình mặc định
Bộ cài đóng gói file **[`config.default.yaml`](../config.default.yaml)** (KHÔNG phải `config.yaml` của máy dev). File này:
- **không chứa tài khoản/mật khẩu** (`users: []`) — site mới sẽ tự sinh mật khẩu admin riêng;
- chứa sẵn danh sách *Nơi thực hiện* mẫu, IP PACS/RIS mẫu — sửa lại nếu muốn mặc định khác.

### 3.3. Build Gateway Server
Nhấp đúp **`build_setup_installer.bat`**:

| Bước | Script tự làm | Kết quả |
|---|---|---|
| 1/2 | Gọi `build_server_exe.bat` → PyInstaller theo `TTSG_DicomGateway.spec` | `dist\TTSG_DicomGateway\` |
| 2/2 | Inno Setup nén thành bộ cài | **`dist\TTSG_DicomGateway_Setup_v2.x.exe`** |

- Script **tự hủy bản build** nếu phát hiện private key lọt vào thư mục phát hành.
- Chỉ cần thư mục chạy (không cần Setup.exe, ví dụ để làm bản vá): chạy riêng `build_server_exe.bat`.
- **Không** chạy thử `run_server.bat` bên trong `dist\` (sẽ sinh dữ liệu thử vào thư mục phát hành).

### 3.4. Build Client Agent (máy trạm)
Nhấp đúp **`Client\build_client_exe.bat`** → kết quả: thư mục **`Client\dist\TTSG_ClientAgent\`** gồm `TTSG_ClientAgent.exe` + `client_config.yaml`. Máy trạm **không cần cài Python**.

---

## 4. CÀI ĐẶT GATEWAY SERVER TẠI BỆNH VIỆN

👤 **Kỹ sư triển khai + IT bệnh viện** · 💻 **Máy chủ Gateway**

### 4.1. Khảo sát thông số (gửi IT bệnh viện điền trước)

| Hạng mục | Ví dụ |
|---|---|
| PACS: IP / Port / AE Title | `192.168.6.213` / `6002` / `PACSTTSG` |
| RIS Worklist: IP / Port / AE Title | `192.168.6.211` / `6002` / `RISTTSG` |
| AE Title của Gateway đăng ký với PACS/RIS | `DICOM_GATEWAY` |
| IP máy Gateway: NIC 1 (mạng phòng khám) / NIC 2 (mạng PACS) | `192.168.0.3` / `192.168.6.200` |

📌 Nhờ IT bệnh viện **khai báo node mới trên PACS**: AE `DICOM_GATEWAY` – IP `192.168.6.200` (NIC 2) – Port `105` (Storage Commitment).

### 4.2. Cấu hình mạng 2 card (Dual-NIC)
- **NIC 1** `192.168.0.3` / `255.255.255.0` — điền Default Gateway của mạng bệnh viện.
- **NIC 2** `192.168.6.200` / `255.255.255.0` — **ĐỂ TRỐNG Default Gateway** (tránh xung đột định tuyến).

### 4.3. Chạy bộ cài
1. Chuột phải **`TTSG_DicomGateway_Setup_v2.x.exe`** → *Run as administrator*.
2. Giữ thư mục mặc định `C:\Program Files\TTSG DICOM Gateway` → **Next** → **Install**.
3. Bộ cài tự động:
   - đăng ký Windows Service **`TTSG_DicomGateway`** (tự chạy cùng Windows, tự khởi động lại khi lỗi);
   - mở Windows Firewall cổng **5000** (Web) và **105** (Storage Commitment);
   - mở trình duyệt `http://localhost:5000`.

### 4.4. Đăng nhập lần đầu
1. Mở file **`C:\Program Files\TTSG DICOM Gateway\data\initial_admin_password.txt`** — chứa tài khoản `admin` và **mật khẩu ngẫu nhiên riêng của máy này**.
2. Đăng nhập `http://localhost:5000` bằng tài khoản đó.
3. **Đổi mật khẩu ngay**: bấm biểu tượng 🔒 *Đổi mật khẩu* trên thanh tiêu đề (tối thiểu 6 ký tự). File mật khẩu ban đầu **tự xóa** sau khi đổi.

### 4.5. Cấu hình kết nối
1. Tab **Cấu hình PACS & RIS** → nhập IP / Port / AE Title của PACS và RIS → **Lưu** → service tự khởi động lại, trang tự tải lại sau ~10 giây.
2. Bấm **Kiểm tra kết nối PACS (C-ECHO)** và **Kiểm tra kết nối RIS (C-ECHO)** → cả hai phải báo **THÀNH CÔNG**.
3. Tab **Nơi Thực Hiện**: thêm / sửa các phòng (Siêu âm, Nội soi…) và modality được phép của từng phòng.
4. Tab **Người Dùng**: tạo tài khoản cho bác sĩ / KTV nếu cần (bắt buộc đặt mật khẩu ≥ 6 ký tự). KTV cũng có thể vào thẳng bằng cách chọn *Nơi thực hiện* ở màn hình đăng nhập, không cần mật khẩu.
5. Tab **Bản Quyền & Hệ Thống**: ghi lại **Hardware ID** để cấp license ([mục 6](#6-cấp--kích-hoạt-license)).

> Hệ thống chạy được ngay ở chế độ **dùng thử 30 ngày** — có thể nghiệm thu trước, cấp license sau.

---

## 5. CÀI ĐẶT MÁY TRẠM (CLIENT AGENT)

Có 2 cách cho máy trạm — chọn theo nhu cầu:

| Cách | Khi nào dùng | Cần cài gì |
|---|---|---|
| **A. Dùng trình duyệt** | KTV tự kéo-thả kết quả, chọn ca từ Worklist | Không cần cài — mở `http://192.168.0.3:5000`, chọn *Nơi thực hiện* |
| **B. Client Agent tự động** | Máy y tế tự xuất file ra thư mục, muốn gửi ngầm không thao tác | `TTSG_ClientAgent` |

### 5.1. Tạo mã kết nối cho trạm (trên Web Gateway)
👤 **Admin** · 💻 **Trình duyệt bất kỳ**

1. Tab **Nơi Thực Hiện** → ở dòng của phòng tương ứng bấm **🔑 Tạo mã Client Agent**.
2. Sao chép mã hiển thị (dạng `ttsg_xxxxxxxx…`).
   - Xem lại mã: bấm **🔑 Mã Client Agent**.
   - Mã bị lộ / máy trạm bị thay: bấm **Tạo lại** → mã cũ ngừng hoạt động ngay.

> Mỗi mã gắn với **một Nơi thực hiện**: file gửi lên bằng mã này chỉ được phép thuộc modality của phòng đó.

### 5.2. Cài trên máy trạm
👤 **Kỹ sư triển khai** · 💻 **Máy trạm phòng khám**

1. Chép thư mục **`TTSG_ClientAgent`** vào máy trạm, ví dụ `C:\TTSG_ClientAgent\`.
2. Mở **`client_config.yaml`**, sửa:
   ```yaml
   server_url: "http://192.168.0.3:5000"     # IP NIC 1 của Gateway
   watch_folder: "C:/ExportImage"            # thư mục máy y tế xuất ảnh/PDF
   sent_folder: "C:/ExportImage/sent"
   failed_folder: "C:/ExportImage/failed"
   station_key: "ttsg_xxxxxxxxxxxxxxxx"      # mã ở bước 5.1
   ```
3. Chạy **`TTSG_ClientAgent.exe`** → thấy `Đang lắng nghe file ảnh/PDF mới...` là được.
4. Tự chạy cùng Windows: `Win + R` → gõ `shell:startup` → tạo shortcut của `TTSG_ClientAgent.exe` vào thư mục vừa mở.

**Quy ước tên file** để Gateway tự lấy thông tin bệnh nhân: `MABN_HoTen_YYYYMMDD.jpg` (ví dụ `BN001_NguyenVanA_20261014.jpg`). Nếu RIS bật, Gateway tra RIS theo mã bệnh nhân để bổ sung thông tin.

**Kiểm tra:** chép 1 file ảnh mẫu vào `watch_folder` → file chuyển sang `sent\`, và ca xuất hiện ở tab **Đã Hoàn Thành** trên Web.

---

## 6. CẤP & KÍCH HOẠT LICENSE

### 6.1. Chính sách bản quyền

| Trạng thái | Hệ thống hoạt động thế nào |
|---|---|
| **DEMO** (chưa có license, ≤ 30 ngày kể từ lần chạy đầu) | Đầy đủ chức năng, tối đa 10 Nơi thực hiện |
| **VALID** | Theo gói: danh sách modality được phép, số Nơi thực hiện tối đa, hạn dùng |
| **EXPIRED / INVALID_SIGNATURE / HARDWARE_MISMATCH** | **Từ chối nhận ca mới**. Upload trên Web: báo lỗi, file vẫn ở máy người dùng. Thư mục theo dõi: file gốc được giữ trong `data\failed\`. Client Agent: file nằm lại máy trạm. Hàng đợi gửi lại PACS **vẫn chạy** — không mất dữ liệu đã nhận |
| Modality không có trong license | Ca của modality đó bị từ chối, các modality khác vẫn chạy |

### 6.2. Lấy Hardware ID
👤 **IT bệnh viện / Kỹ sư triển khai** · 💻 **Máy chủ Gateway**

Tab **Bản Quyền & Hệ Thống** → bấm **Sao Chép** cạnh mã máy (dạng `TTSG-6F6E-BCA7-82EA-C52B`) → gửi cho nhà phát triển.

### 6.3. Tạo file license
👤 **Nhà phát triển** · 💻 **Máy phát triển (có `keys\license_private.pem`)**

**Cách nhanh:** nhấp đúp **`tao_license.bat`** và trả lời 5 câu hỏi:

| Hỏi | Nhập | Mặc định khi Enter |
|---|---|---|
| 1. Tên bệnh viện | `BV Đa khoa ABC` | BV Tam Tri Sai Gon |
| 2. Hardware ID | `TTSG-6F6E-BCA7-82EA-C52B` | `*` = **mọi máy** (chỉ dùng nội bộ, KHÔNG cấp cho khách) |
| 3. Hạn dùng | `2027-12-31` | `PERMANENT` (vĩnh viễn) |
| 4. Số Nơi thực hiện tối đa | `20` | 100 |
| 5. Modality được phép | `US,ES,ECG` | `*` = tất cả |

→ Kết quả: **`data\license.key`**. Đổi tên cho dễ quản lý (ví dụ `license_BV_ABC_2027.key`) rồi gửi cho bệnh viện.

**Cách dòng lệnh** (đặt tên gói, xuất thẳng ra file riêng):
```bat
.venv\Scripts\python.exe license_generator.py --customer "BV Đa khoa ABC" --hwid "TTSG-6F6E-BCA7-82EA-C52B" ^
    --exp 2027-12-31 --modalities "US,ES,ECG" --stations 20 --plan "Enterprise Medical Edition" ^
    --out "license_BV_ABC_2027.key"
```

### 6.4. Kích hoạt
👤 **Admin bệnh viện** · 💻 **Trình duyệt**

Tab **Bản Quyền & Hệ Thống** → khu vực **Kích Hoạt Bản Quyền** → chọn (hoặc kéo-thả) file `.key` → bấm **Kích Hoạt Bản Quyền** → trạng thái **VALID** là xong. Không cần khởi động lại.

*Cách thay thế:* chép file vào `C:\Program Files\TTSG DICOM Gateway\data\license.key` rồi khởi động lại service.

### 6.5. Gia hạn / đổi phần cứng
- **Gia hạn, thêm modality, thêm trạm:** tạo license mới với cùng Hardware ID → kích hoạt đè lên.
- **Hardware ID thay đổi khi:** đổi **tên máy tính**, thay mainboard, thay card mạng, cài lại Windows. Khi đó license báo `HARDWARE_MISMATCH` → lấy Hardware ID mới (6.2) và cấp lại.

---

## 7. CẬP NHẬT PHIÊN BẢN

Dù dùng cách nào, các thứ sau **luôn được giữ nguyên**: `config.yaml`, thư mục `data\` (CSDL lịch sử ca, license, hàng đợi retry), `logs\`.

### 7.1. Cách A — Bản vá `.pkg` qua Web (khuyến nghị cho cập nhật thường xuyên)

👤 **Nhà phát triển** · 💻 **Máy phát triển**
1. Chạy **`build_server_exe.bat`** (tạo `dist\TTSG_DicomGateway\` mới).
2. Chạy **`build_patch.bat`** → nhập số phiên bản (ví dụ `2.1.1`) và ghi chú.
3. Kết quả: **`TTSG_Gateway_Patch_v2.1.1.pkg`** ở thư mục gốc dự án → gửi cho bệnh viện.

👤 **Admin bệnh viện** · 💻 **Trình duyệt**
1. Tab **Bản Quyền & Hệ Thống** → mục nâng cấp bằng bản vá → chọn file `.pkg` → bấm **Cập Nhật Ngay**.
2. Hệ thống kiểm tra chữ ký số + mã băm từng file → ghi đè chương trình → **service tự khởi động lại sau vài giây**.
3. Đợi ~10 giây rồi tải lại trang (F5).

> Gói `.pkg` chỉ chứa chương trình & giao diện. Nếu phiên bản mới cần **thêm mục cấu hình mới**, phải bổ sung tay vào `config.yaml` tại site (ghi chú trong release note).

### 7.2. Cách B — Chạy Setup.exe mới đè lên bản cũ
1. Build bộ cài mới ([mục 3](#3-build-bộ-cài)).
2. Tại máy chủ: chạy `TTSG_DicomGateway_Setup_vX.exe` (Run as administrator) → **Install**.
3. Bộ cài tự **dừng service → chép file mới → chạy lại service**.

**Quay về phiên bản trước (rollback):** chạy lại Setup.exe của phiên bản cũ (giữ lại các bộ cài đã phát hành).

### 7.3. Lần nâng cấp đầu tiên sau khi đổi khóa (BẮT BUỘC LÀM)
Các site đang chạy bản build **trước ngày 14/10/2026** chỉ tin khóa cũ, nên:
1. **Bắt buộc dùng Cách B (Setup.exe)** — file `.pkg` mới sẽ bị từ chối vì "chữ ký không hợp lệ".
2. Sau khi cài, license cũ báo **INVALID_SIGNATURE** → **cấp lại license** ([mục 6](#6-cấp--kích-hoạt-license)) và kích hoạt ngay, nếu không Gateway sẽ từ chối nhận ca mới.
3. Kiểm tra `config.yaml` của site: nếu còn các tài khoản mẫu (`ktv_*`…) dùng chung mật khẩu thì **đổi mật khẩu hoặc xóa** ở tab **Người Dùng**.
4. Nếu site dùng Client Agent: tạo mã kết nối cho từng trạm ([mục 5.1](#51-tạo-mã-kết-nối-cho-trạm-trên-web-gateway)) và cập nhật Client Agent bản mới có `station_key`.

Từ lần sau trở đi dùng Cách A bình thường.

---

## 8. ĐỔI MÁY CHỦ / ĐỔI IP / ĐỔI PORT

> **Quy tắc chung:** khi lưu thay đổi ở tab **Cấu hình PACS & RIS** (hoặc các mục kết nối, thư mục, port) trên Web, service **tự khởi động lại** sau ~2 giây để mọi luồng (thư mục theo dõi, hàng đợi gửi lại, tra cứu RIS, Web) dùng chung cấu hình mới; trang Web tự tải lại khi service lên lại. Nếu sửa tay `config.yaml` thì phải tự khởi động lại: `net stop TTSG_DicomGateway & net start TTSG_DicomGateway`.
> Mỗi lần khởi động, service **tự mở Windows Firewall đúng port** đang cấu hình (`web_ui.port`, `pacs.storage_commitment.listen_port`) — không cần chạy `netsh` bằng tay.

### 8.1. PACS hoặc RIS đổi IP / Port / AE Title
👤 **Admin** · 💻 **Trình duyệt**
1. Tab **Cấu hình PACS & RIS** → sửa thông số → **Lưu** → đợi trang tự tải lại (~10 giây).
2. Bấm **Kiểm tra kết nối PACS (C-ECHO)** / **RIS (C-ECHO)** → phải báo THÀNH CÔNG.
3. Nhờ IT bệnh viện khai báo node `DICOM_GATEWAY` (IP NIC 2 của Gateway, port Storage Commitment) trên **PACS mới**.
4. Ca đang nằm trong hàng đợi gửi lại sẽ tự gửi tới PACS mới ở lần thử kế tiếp (hoặc bấm **Thử lại ngay** ở tab **Đã Hoàn Thành**).

### 8.2. Gateway đổi địa chỉ IP (vẫn máy cũ)
- **License không bị ảnh hưởng** (Hardware ID không phụ thuộc IP).
- **NIC 1 (mạng phòng khám) đổi IP:** sửa `server_url` trong `client_config.yaml` của **mọi máy trạm** dùng Client Agent rồi chạy lại agent; máy trạm dùng trình duyệt mở địa chỉ mới.
- **NIC 2 (mạng PACS) đổi IP:** nhờ IT sửa IP của node `DICOM_GATEWAY` trên PACS (PACS gửi Storage Commitment ngược về IP này).

### 8.3. Đổi port Web (mặc định 5000)
1. Tab **Cấu hình PACS & RIS** (hoặc `config.yaml`): `web_ui.port: 8080` → **Lưu**.
2. Service tự khởi động lại trên port mới, tự mở firewall port mới; trình duyệt tự chuyển sang `http://<IP>:8080/` sau ~12 giây.
3. Sửa `server_url: "http://<IP>:8080"` trên **mọi Client Agent**.
4. Shortcut *Control Panel* trên Desktop/Start Menu vẫn trỏ `localhost:5000` → dùng địa chỉ mới (hoặc sửa shortcut).

### 8.4. Đổi port Storage Commitment (mặc định 105)
1. `pacs.storage_commitment.listen_port` → **Lưu** (service tự khởi động lại, tự mở firewall).
2. Nhờ IT sửa port callback của node `DICOM_GATEWAY` trên PACS cho khớp.

### 8.5. Chuyển Gateway sang máy chủ mới
👤 **Kỹ sư triển khai** · 💻 **Máy cũ + máy mới**
1. Cài Setup.exe trên máy mới (mục 4.3), cấu hình 2 card mạng (mục 4.2).
2. Máy cũ: `net stop TTSG_DicomGateway`.
3. Chép từ máy cũ sang máy mới (thư mục cài đặt), **ghi đè**:
   - `config.yaml` — giữ nguyên PACS/RIS, tài khoản, Nơi thực hiện **và mã Client Agent** (máy trạm không phải đổi `station_key`);
   - toàn bộ `data\` — lịch sử ca, hàng đợi gửi lại, file gốc. **Trừ** `license.key` và `.trial.json`.
4. Máy mới: `net start TTSG_DicomGateway` → đăng nhập bằng tài khoản cũ.
5. **Cấp license mới** cho Hardware ID của máy mới (mục 6) — license cũ sẽ báo `HARDWARE_MISMATCH`.
6. Nếu IP máy mới khác máy cũ: làm thêm mục 8.2.
7. Gỡ cài đặt trên máy cũ (Control Panel → Programs → *TTSG DICOM Gateway*) để tránh 2 Gateway cùng gửi PACS.

---

## 9. VẬN HÀNH & XỬ LÝ SỰ CỐ

### 9.1. Lệnh quản trị (CMD / PowerShell **Run as administrator**)

| Việc | Lệnh |
|---|---|
| Xem trạng thái | `sc query TTSG_DicomGateway` |
| Dừng / chạy | `net stop TTSG_DicomGateway` · `net start TTSG_DicomGateway` |
| Xem log trực tiếp | `Get-Content "C:\Program Files\TTSG DICOM Gateway\logs\gateway.log" -Tail 50 -Wait` |
| Cài lại service / mở lại firewall | Chạy `service_install.bat` trong thư mục cài đặt (Run as administrator) |
| Chỉ mở lại firewall theo port trong config | `TTSG_DicomGateway.exe --configure-firewall` (trong thư mục cài đặt, quyền Admin) |

Trên máy phát triển có thêm công cụ chẩn đoán trong `tools\`: `test_ket_noi_pacs.bat` (C-ECHO PACS), `run_mock_pacs.bat` / `run_mock_ris.bat` (PACS/RIS giả lập để test), `inspect_pacs_query.py`, `inspect_worklist_raw.py`.

### 9.2. Bảng sự cố thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không biết mật khẩu admin sau khi cài | — | Xem `data\initial_admin_password.txt` (chỉ còn nếu chưa đổi mật khẩu) |
| Quên mật khẩu admin đã đổi | — | Dừng service → xóa toàn bộ mục `users:` trong `config.yaml` (để `users: []`) → chạy service → hệ thống tạo lại `admin` + file mật khẩu mới |
| Client Agent log `⛔ AUTH: Gateway từ chối xác thực (HTTP 401/403)` | Thiếu/sai `station_key`, mã đã bị *Tạo lại*, hoặc modality không thuộc phòng | Lấy mã ở tab **Nơi Thực Hiện** → sửa `client_config.yaml` → chạy lại agent. File vẫn nằm chờ trong thư mục, không bị mất |
| Ca bị từ chối "Bản quyền không hợp lệ…" / "Modality … không nằm trong gói" | Hết hạn dùng thử / license sai máy / thiếu modality | Cấp & kích hoạt license (mục 6) → chép lại file từ `data\failed\` vào thư mục inbox, hoặc upload lại trên Web |
| Test PACS báo Timeout / Connection refused | Sai IP/Port/AE, PACS chưa khai báo node `DICOM_GATEWAY`, firewall | `ping` IP PACS; nhờ IT khai báo node (mục 4.1); kiểm tra lại tab Cấu hình (mục 8.1) |
| Test RIS OK nhưng Worklist trống | Sai AE RIS, ngày lọc không có ca | Thử ngày khác; kiểm tra `called_ae_title` của RIS |
| Máy trạm không mở được trang Web Gateway | Sai port (đã đổi `web_ui.port`?), firewall, khác lớp mạng | Kiểm tra `web_ui.port` trong `config.yaml`; chạy `TTSG_DicomGateway.exe --configure-firewall` (Admin); `ping` IP Gateway từ máy trạm |
| Đã gửi PACS nhưng PACS Viewer không hiện | PACS yêu cầu Storage Commitment | Bật `pacs.storage_commitment.enabled: true`, nhờ IT trỏ callback về cổng 105 của Gateway |
| Cập nhật `.pkg` báo "Chữ ký số … không hợp lệ" | Gói ký bằng khóa khác với bản đang cài (thường do lần đầu sau đổi khóa) | Làm theo mục 7.3 (dùng Setup.exe) |
| Tài khoản bị khóa 5 phút | Nhập sai mật khẩu 5 lần | Chờ 5 phút hoặc khởi động lại service |

---

## 10. PHỤ LỤC: VỊ TRÍ FILE & CHECKLIST BẢO MẬT

### 10.1. Vị trí file trên máy chủ (`C:\Program Files\TTSG DICOM Gateway\`)

| Đường dẫn | Nội dung | Cập nhật có ghi đè? |
|---|---|---|
| `TTSG_DicomGateway.exe`, `_internal\` | Chương trình | Có |
| `config.yaml` | Cấu hình site (PACS/RIS, tài khoản, Nơi thực hiện, mã Client Agent) | **Không** |
| `data\license.key` | License đã kích hoạt | **Không** |
| `data\registry.sqlite3` | Lịch sử ca chụp, chống trùng | **Không** |
| `data\processed\`, `failed\`, `duplicates\`, `queue\retry\` | File gốc, file lỗi, hàng đợi gửi lại | **Không** |
| `data\initial_admin_password.txt` | Mật khẩu admin ban đầu (tự xóa khi đổi mật khẩu) | **Không** |
| `logs\gateway.log` | Nhật ký hệ thống | **Không** |

### 10.2. Checklist bảo mật mỗi lần phát hành
- [ ] `keys\license_private.pem` đã sao lưu, **không** có trong Git, không gửi cho ai.
- [ ] Build bằng `build_server_exe.bat` / `build_setup_installer.bat` (có chặn lộ private key) — không build tay bằng lệnh PyInstaller khác.
- [ ] `config.default.yaml` không chứa tài khoản/mật khẩu; `config.yaml` không nằm trong Git.
- [ ] Không cấp license `Hardware ID = *` cho khách hàng.
- [ ] Sau khi cài: admin đã đổi mật khẩu, file `initial_admin_password.txt` đã biến mất.
- [ ] Mỗi Client Agent dùng mã riêng của phòng mình; máy trạm thanh lý → bấm **Tạo lại** mã.

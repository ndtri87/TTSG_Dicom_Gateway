"""Hệ thống Quản lý Bản quyền & Khóa phần cứng (Hardware-Locked RSA Licensing)
Phục vụ đóng gói thương mại phần mềm y tế TTSG DICOM Gateway."""

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from datetime import datetime, date, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# Master RSA 2048-bit Public Key nhúng sẵn vào Gateway Server.
# Private key tương ứng nằm NGOÀI repo (keys/license_private.pem, xem license_generator.py).
# Cặp khóa được thay mới ngày 2026-10-14 do khóa cũ bị lộ — license/bản vá ký bằng khóa cũ không còn hợp lệ.
DEFAULT_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvjuw3MQnnVIUdAG+qDKl
l/cGy4qSVTLYeNaCc+ybZqGMmMJ/MzHS2PfUP/RH7eaJuxHRrR1fo0nZBiGhT2/g
929HNxWRTKeYTfWhWnFIJTEKzPFoJ/CO5BSLVloThli+sMZ5fGvvRluaLrPulLjl
ttLnzIqMWcxkltF6GpK/t0U1QEL6YEsmjHq3v2Pspn72IqUs5TSWXNYaqA87CySo
efj9/qQs+snr0TBpnvhLqmN19d+VXWtVb0jvO2m5K4WJte8eTkxO/WiEDy30jWbE
tztL7FErUCmAEOILCzvxcJL0IPuPvq702wesKdY3LM9fib5lZrLvILHTNBLDabBv
1QIDAQAB
-----END PUBLIC KEY-----"""


def get_machine_fingerprint() -> str:
    """Thu thập thông tin định danh phần cứng duy nhất của máy tính (CPU, Mainboard, MachineGuid, MAC)."""
    components = []

    # 1. Tên máy / Node
    components.append(platform.node())
    components.append(platform.machine())

    # 2. MAC Address phần cứng
    try:
        mac_num = uuid.getnode()
        components.append(str(mac_num))
    except Exception:
        pass

    # 3. Thu thập thông tin Windows MachineGuid từ Registry hoặc BIOS UUID
    if platform.system() == 'Windows':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                if guid:
                    components.append(str(guid))
        except Exception:
            pass

        try:
            cmd = "powershell -NoProfile -Command \"(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID\""
            out = subprocess.check_output(cmd, shell=True, timeout=2, stderr=subprocess.DEVNULL).decode('utf-8', errors='ignore').strip()
            if out:
                components.append(out)
        except Exception:
            pass

    # Kết hợp các thành phần và băm SHA-256
    raw_str = "|".join(filter(None, components))
    sha256_hash = hashlib.sha256(raw_str.encode('utf-8')).hexdigest().upper()

    # Định dạng thành mã Hardware ID đẹp: TTSG-XXXX-XXXX-XXXX-XXXX (16 ký tự hex)
    sub = sha256_hash[:16]
    return f"TTSG-{sub[0:4]}-{sub[4:8]}-{sub[8:12]}-{sub[12:16]}"


class LicenseManager:
    """Quản lý trạng thái và xác thực chữ ký bản quyền RSA 2048-bit."""

    REFRESH_INTERVAL_SEC = 300

    def __init__(self, license_path: str = None, public_key_pem: str = None):
        if license_path:
            self.license_path = license_path
        else:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            self.license_path = os.path.join(base_dir, 'data', 'license.key')

        self.public_key_pem = public_key_pem or DEFAULT_PUBLIC_KEY_PEM
        self.current_hardware_id = get_machine_fingerprint()
        self._cached_status = None
        self._evaluated_at = 0.0
        self.evaluate_license()

    def _get_demo_trial_info(self) -> dict:
        """Lấy hoặc khởi tạo thông tin bản dùng thử giới hạn 1 tháng (30 ngày)."""
        # Lưu cạnh license.key (thư mục data/ của bản cài), không dùng __file__ vì
        # khi đóng gói PyInstaller __file__ trỏ vào _internal/.
        trial_file = os.path.join(os.path.dirname(os.path.abspath(self.license_path)), '.trial.json')
        os.makedirs(os.path.dirname(trial_file), exist_ok=True)
        now_dt = datetime.now()

        trial_data = None
        if os.path.exists(trial_file):
            try:
                with open(trial_file, 'r', encoding='utf-8') as f:
                    trial_data = json.load(f)
            except Exception:
                trial_data = None

        if not trial_data or 'installed_at' not in trial_data:
            trial_data = {
                'installed_at': now_dt.isoformat(),
                'trial_days': 30,
                'hardware_id': self.current_hardware_id
            }
            try:
                with open(trial_file, 'w', encoding='utf-8') as f:
                    json.dump(trial_data, f, indent=2)
            except Exception:
                pass

        try:
            installed_date = datetime.fromisoformat(trial_data.get('installed_at')).date()
        except Exception:
            installed_date = date.today()

        trial_days = trial_data.get('trial_days', 30)
        exp_date = installed_date + timedelta(days=trial_days)
        today = date.today()
        days_left = (exp_date - today).days

        is_expired = days_left < 0
        days_remaining = max(0, days_left)

        return {
            'installed_date': installed_date.strftime('%Y-%m-%d'),
            'expiration_date': exp_date.strftime('%Y-%m-%d'),
            'days_remaining': days_remaining,
            'is_expired': is_expired,
            'trial_days': trial_days
        }

    def evaluate_license(self) -> dict:
        """Đọc và đánh giá tính hợp lệ của file license hiện tại."""
        self._evaluated_at = time.monotonic()
        if not os.path.exists(self.license_path):
            trial = self._get_demo_trial_info()
            if trial['is_expired']:
                self._cached_status = {
                    'status': 'EXPIRED',
                    'is_valid': False,
                    'is_demo': True,
                    'plan_name': 'Bản Dùng Thử 30 Ngày (Đã Hết Hạn)',
                    'customer_name': 'Khách Hàng Dùng Thử',
                    'hardware_id': self.current_hardware_id,
                    'expiration_date': trial['expiration_date'],
                    'days_remaining': 0,
                    'max_stations': 10,
                    'allowed_modalities': ['*'],
                    'message': f'Bản dùng thử 30 ngày đã hết hạn vào ngày {trial["expiration_date"]}. Vui lòng kích hoạt bản quyền thương mại.',
                }
            else:
                self._cached_status = {
                    'status': 'DEMO',
                    'is_valid': True,
                    'is_demo': True,
                    'plan_name': 'Bản Dùng Thử 30 Ngày (Demo 30-Day Edition)',
                    'customer_name': 'Khách Hàng Dùng Thử',
                    'hardware_id': self.current_hardware_id,
                    'expiration_date': trial['expiration_date'],
                    'days_remaining': trial['days_remaining'],
                    'max_stations': 10,
                    'allowed_modalities': ['*'],
                    'message': f'Đang hoạt động ở chế độ Dùng Thử 30 ngày (Còn {trial["days_remaining"]} ngày). Vui lòng đăng ký bản quyền thương mại.',
                }
            return self._cached_status

        try:
            with open(self.license_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            info = self.verify_license_data(content)
            if not info.get('is_valid'):
                # Kết quả lỗi phải đủ trường để giao diện không hiện "undefined ngày" / "Không giới hạn" trạm
                for key, default in (('is_demo', False), ('plan_name', 'Không Hợp Lệ'), ('customer_name', 'N/A'),
                                     ('hardware_id', self.current_hardware_id), ('expiration_date', 'N/A'),
                                     ('days_remaining', 0), ('max_stations', 0), ('allowed_modalities', [])):
                    info.setdefault(key, default)
            self._cached_status = info
            return info
        except Exception as exc:
            self._cached_status = {
                'status': 'CORRUPT',
                'is_valid': False,
                'is_demo': False,
                'plan_name': 'Không Hợp Lệ',
                'customer_name': 'N/A',
                'hardware_id': self.current_hardware_id,
                'expiration_date': 'N/A',
                'days_remaining': 0,
                'max_stations': 0,
                'allowed_modalities': [],
                'message': f'File bản quyền bị lỗi hoặc không thể đọc: {exc}',
            }
            return self._cached_status

    def verify_license_data(self, license_str: str) -> dict:
        """Xác thực chuỗi license mã hóa base64 bằng RSA Public Key."""
        try:
            raw_json = base64.b64decode(license_str.encode('utf-8')).decode('utf-8')
            payload = json.loads(raw_json)
        except Exception:
            return {
                'status': 'INVALID_FORMAT',
                'is_valid': False,
                'message': 'Định dạng file bản quyền không đúng chuẩn mã hóa Base64 JSON.'
            }

        signature_b64 = payload.get('signature', '')
        data_dict = payload.get('data', {})

        if not signature_b64 or not data_dict:
            return {
                'status': 'INVALID_FORMAT',
                'is_valid': False,
                'message': 'Thiếu chữ ký số RSA hoặc dữ liệu bản quyền.'
            }

        # 1. Xác thực chữ ký số RSA
        try:
            pub_key = load_pem_public_key(self.public_key_pem.encode('utf-8'))
            signature = base64.b64decode(signature_b64.encode('utf-8'))
            # Dữ liệu được ký là chuỗi JSON sắp xếp keys chuẩn
            canonical_data = json.dumps(data_dict, sort_keys=True).encode('utf-8')

            pub_key.verify(
                signature,
                canonical_data,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
        except Exception:
            return {
                'status': 'INVALID_SIGNATURE',
                'is_valid': False,
                'hardware_id': self.current_hardware_id,
                'message': 'Chữ ký bản quyền không hợp lệ hoặc đã bị chỉnh sửa trái phép!'
            }

        # 2. Kiểm tra Hardware ID
        lic_hwid = data_dict.get('hardware_id', '').strip().upper()
        if lic_hwid != '*' and lic_hwid != self.current_hardware_id:
            return {
                'status': 'HARDWARE_MISMATCH',
                'is_valid': False,
                'customer_name': data_dict.get('customer_name', 'N/A'),
                'hardware_id': self.current_hardware_id,
                'license_hardware_id': lic_hwid,
                'message': f'Bản quyền này được cấp cho máy khác ({lic_hwid}). Mã máy hiện tại là {self.current_hardware_id}.'
            }

        # 3. Kiểm tra ngày hết hạn
        exp_date_str = data_dict.get('expiration_date', '2099-12-31')
        days_left = 999
        is_expired = False

        if exp_date_str.upper() != 'PERMANENT':
            try:
                exp_d = datetime.strptime(exp_date_str, '%Y-%m-%d').date()
                today_d = date.today()
                days_left = (exp_d - today_d).days
                if days_left < 0:
                    is_expired = True
            except ValueError:
                pass

        if is_expired:
            return {
                'status': 'EXPIRED',
                'is_valid': False,
                'plan_name': data_dict.get('plan_name', 'Commercial License'),
                'customer_name': data_dict.get('customer_name', 'Khách hàng'),
                'hardware_id': self.current_hardware_id,
                'expiration_date': exp_date_str,
                'days_remaining': days_left,
                'max_stations': data_dict.get('max_stations', 99),
                'allowed_modalities': data_dict.get('allowed_modalities', ['*']),
                'message': f'Bản quyền phần mềm đã hết hạn vào ngày {exp_date_str}. Vui lòng gia hạn hợp đồng.'
            }

        return {
            'status': 'VALID',
            'is_valid': True,
            'is_demo': False,
            'plan_name': data_dict.get('plan_name', 'Bản Quyền Doanh Nghiệp (Enterprise)'),
            'customer_name': data_dict.get('customer_name', 'Bệnh viện Đa khoa Tâm Trí Sài Gòn'),
            'hardware_id': self.current_hardware_id,
            'expiration_date': exp_date_str,
            'days_remaining': days_left,
            'max_stations': data_dict.get('max_stations', 50),
            'allowed_modalities': data_dict.get('allowed_modalities', ['*']),
            'message': 'Bản quyền phần mềm chính hãng đang hoạt động tốt.',
        }

    def activate_license(self, license_content: str) -> dict:
        """Kích hoạt và lưu file license mới."""
        res = self.verify_license_data(license_content.strip())
        if not res.get('is_valid'):
            return res

        # Lưu file license.key vào thư mục
        os.makedirs(os.path.dirname(os.path.abspath(self.license_path)), exist_ok=True)
        with open(self.license_path, 'w', encoding='utf-8') as f:
            f.write(license_content.strip())

        self.evaluate_license()
        return self._cached_status

    def _refresh_if_stale(self):
        # Service chạy 24/7: đánh giá lại định kỳ để bản dùng thử / license hết hạn có hiệu lực ngay
        if time.monotonic() - self._evaluated_at > self.REFRESH_INTERVAL_SEC:
            self.evaluate_license()

    def is_modality_licensed(self, modality_code: str) -> bool:
        """Kiểm tra một modality có nằm trong gói bản quyền đã mua hay không."""
        self._refresh_if_stale()
        if not self._cached_status or not self._cached_status.get('is_valid'):
            return False
        allowed = self._cached_status.get('allowed_modalities', ['*'])
        if '*' in allowed or 'ALL' in allowed:
            return True
        return (modality_code or '').strip().upper() in [m.upper() for m in allowed]

    def check_processing_allowed(self, modality_code: str) -> tuple[bool, str]:
        """Có được phép chuyển đổi & gửi ca mới với modality này không. Trả về (ok, lý do)."""
        if self.is_modality_licensed(modality_code):
            return True, ''
        status = self._cached_status or {}
        if not status.get('is_valid'):
            return False, f"Bản quyền không hợp lệ ({status.get('status', 'UNKNOWN')}): {status.get('message', '')}"
        return False, f"Modality [{modality_code}] không nằm trong gói bản quyền đã cấp ({', '.join(status.get('allowed_modalities', []))})."

    def max_stations(self) -> int:
        self._refresh_if_stale()
        return int((self._cached_status or {}).get('max_stations') or 0)

    def get_summary(self) -> dict:
        """Lấy thông tin tổng hợp cho Web API."""
        return self.evaluate_license()

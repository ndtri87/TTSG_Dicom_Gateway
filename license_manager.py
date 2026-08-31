"""Hệ thống Quản lý Bản quyền & Khóa phần cứng (Hardware-Locked RSA Licensing)
Phục vụ đóng gói thương mại phần mềm y tế TTSG DICOM Gateway."""

import base64
import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, date, timedelta

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key

# Master RSA 2048-bit Public Key nhúng sẵn vào Gateway Server
DEFAULT_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA0IcXv5cCAsHgcTwc7Gj+
O2cLRzvlMRh71MnPgHPoqTMnmnt6sdElW+4GlzKZgMCkaRIE3VFCjcEsxrKxFyEm
SNKyuMH9LM4O3Q3E3FQ/t9/7cr+29fnhw9nYlQLZjWfJls65K+kWhejVyxOYUKbJ
4HPq7EW4hQ6ESY4KBygB+C8MDAFZdCdjCKJDH2Arj4tuD3bKKKv0SMFxNKxb6Dtj
U43JYMngY5XYwyqtWAZUepy7vGsTdtzO7Ngpg7nEYKYYWgTJOoKidZiCJ/Gcequ5
P2AUxaEj1Z04/bDI4G+XkpidgdU3GuHqrSIaw6HmYK4fWTAQ1cMEM+MYWpFXLvje
pQIDAQAB
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

    def __init__(self, license_path: str = None, public_key_pem: str = None):
        if license_path:
            self.license_path = license_path
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            data_lic = os.path.join(base_dir, 'data', 'license.key')
            root_lic = os.path.join(base_dir, 'license.key')
            if os.path.exists(data_lic):
                self.license_path = data_lic
            elif os.path.exists(root_lic):
                self.license_path = root_lic
            else:
                self.license_path = data_lic

        self.public_key_pem = public_key_pem or DEFAULT_PUBLIC_KEY_PEM
        self.current_hardware_id = get_machine_fingerprint()
        self._cached_status = None
        self.evaluate_license()

    def _get_demo_trial_info(self) -> dict:
        """Lấy hoặc khởi tạo thông tin bản dùng thử giới hạn 1 tháng (30 ngày)."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        trial_file = os.path.join(base_dir, 'data', '.trial.json')
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

    def is_modality_licensed(self, modality_code: str) -> bool:
        """Kiểm tra một modality có nằm trong gói bản quyền đã mua hay không."""
        if not self._cached_status or not self._cached_status.get('is_valid'):
            return False
        allowed = self._cached_status.get('allowed_modalities', ['*'])
        if '*' in allowed or 'ALL' in allowed:
            return True
        return (modality_code or '').strip().upper() in [m.upper() for m in allowed]

    def get_summary(self) -> dict:
        """Lấy thông tin tổng hợp cho Web API."""
        return self.evaluate_license()

import base64
import json
import os
import sys
import tempfile
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from license_generator import generate_license_data
from license_manager import LicenseManager, get_machine_fingerprint


def test_get_machine_fingerprint_format():
    hwid = get_machine_fingerprint()
    assert hwid.startswith('TTSG-')
    parts = hwid.split('-')
    assert len(parts) == 5
    for p in parts[1:]:
        assert len(p) == 4


def test_license_demo_mode_when_missing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        non_existent = os.path.join(tmp_dir, 'no_such_license.key')
        lm = LicenseManager(license_path=non_existent)
        status = lm.get_summary()

        assert status['status'] == 'DEMO'
        assert status['is_valid'] is True
        assert status['is_demo'] is True
        assert lm.is_modality_licensed('US') is True
        assert lm.is_modality_licensed('CT') is True


def test_license_sign_and_verify_valid():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lic_file = os.path.join(tmp_dir, 'license.key')
        hwid = get_machine_fingerprint()
        exp_date = (date.today() + timedelta(days=365)).strftime('%Y-%m-%d')

        lic_data = generate_license_data(
            customer_name='Bệnh viện Đa khoa Tâm Trí Sài Gòn',
            hardware_id=hwid,
            expiration_date=exp_date,
            allowed_modalities=['US', 'ES', 'ECG'],
            max_stations=25,
            plan_name='Bản Quyền Tiêu Chuẩn'
        )

        with open(lic_file, 'w', encoding='utf-8') as f:
            f.write(lic_data)

        lm = LicenseManager(license_path=lic_file)
        summary = lm.get_summary()

        assert summary['status'] == 'VALID'
        assert summary['is_valid'] is True
        assert summary['customer_name'] == 'Bệnh viện Đa khoa Tâm Trí Sài Gòn'
        assert summary['max_stations'] == 25
        assert summary['days_remaining'] > 360
        assert lm.is_modality_licensed('US') is True
        assert lm.is_modality_licensed('ES') is True
        assert lm.is_modality_licensed('CT') is False


def test_license_hardware_mismatch():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lic_file = os.path.join(tmp_dir, 'license.key')
        lic_data = generate_license_data(
            customer_name='Bệnh viện Khác',
            hardware_id='TTSG-0000-1111-2222-3333',
            expiration_date='2030-01-01',
            allowed_modalities=['*']
        )

        with open(lic_file, 'w', encoding='utf-8') as f:
            f.write(lic_data)

        lm = LicenseManager(license_path=lic_file)
        summary = lm.get_summary()

        assert summary['status'] == 'HARDWARE_MISMATCH'
        assert summary['is_valid'] is False
        assert lm.is_modality_licensed('US') is False


def test_license_expired():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lic_file = os.path.join(tmp_dir, 'license.key')
        hwid = get_machine_fingerprint()
        past_date = (date.today() - timedelta(days=10)).strftime('%Y-%m-%d')

        lic_data = generate_license_data(
            customer_name='Bệnh viện Hết Hạn',
            hardware_id=hwid,
            expiration_date=past_date,
            allowed_modalities=['*']
        )

        with open(lic_file, 'w', encoding='utf-8') as f:
            f.write(lic_data)

        lm = LicenseManager(license_path=lic_file)
        summary = lm.get_summary()

        assert summary['status'] == 'EXPIRED'
        assert summary['is_valid'] is False
        assert summary['days_remaining'] < 0


def test_license_tampered_signature_rejected():
    with tempfile.TemporaryDirectory() as tmp_dir:
        lic_file = os.path.join(tmp_dir, 'license.key')
        hwid = get_machine_fingerprint()

        lic_data = generate_license_data(
            customer_name='Bệnh viện Tâm Trí',
            hardware_id=hwid,
            expiration_date='2030-01-01',
            allowed_modalities=['*']
        )

        # Giải mã và sửa lén customer_name mà không ký lại
        raw_json = base64.b64decode(lic_data.encode('utf-8')).decode('utf-8')
        pkg = json.loads(raw_json)
        pkg['data']['customer_name'] = 'Bệnh viện Bị Sửa Trái Phép'
        tampered_b64 = base64.b64encode(json.dumps(pkg).encode('utf-8')).decode('utf-8')

        with open(lic_file, 'w', encoding='utf-8') as f:
            f.write(tampered_b64)

        lm = LicenseManager(license_path=lic_file)
        summary = lm.get_summary()

        assert summary['status'] == 'INVALID_SIGNATURE'
        assert summary['is_valid'] is False


def test_license_demo_30_day_limit():
    """Kiểm tra bản dùng thử tự động kích hoạt thời hạn 30 ngày (1 tháng)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        non_existent = os.path.join(tmp_dir, 'no_such_license.key')
        lm = LicenseManager(license_path=non_existent)
        summary = lm.get_summary()

        assert summary['status'] == 'DEMO'
        assert summary['is_valid'] is True
        assert summary['is_demo'] is True
        assert summary['days_remaining'] <= 30
        assert summary['days_remaining'] >= 29
        assert '30 Ngày' in summary['plan_name']


def test_license_demo_expired_after_30_days():
    """Kiểm tra bản dùng thử hết hạn khi vượt quá 30 ngày kể từ lúc cài đặt."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        non_existent = os.path.join(tmp_dir, 'no_such_license.key')
        trial_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', '.trial.json')
        
        # Mô phỏng cài đặt từ 35 ngày trước
        os.makedirs(os.path.dirname(trial_file), exist_ok=True)
        with open(trial_file, 'w', encoding='utf-8') as f:
            json.dump({'installed_at': '2026-01-01T00:00:00', 'trial_days': 30}, f)

        try:
            lm = LicenseManager(license_path=non_existent)
            summary = lm.get_summary()

            assert summary['status'] == 'EXPIRED'
            assert summary['is_valid'] is False
            assert summary['days_remaining'] == 0
        finally:
            if os.path.exists(trial_file):
                os.remove(trial_file)


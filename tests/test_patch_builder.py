import io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patch_builder import create_patch_package, verify_and_apply_patch
from utils import hash_password
from web_server import app, init_web_app


def test_create_and_apply_patch_valid():
    with tempfile.TemporaryDirectory() as dev_dir, tempfile.TemporaryDirectory() as client_app_dir:
        # 1. Giả lập thư mục build trên máy phát triển
        templates_dir = os.path.join(dev_dir, 'templates')
        os.makedirs(templates_dir, exist_ok=True)
        with open(os.path.join(templates_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write("<h1>TTSG DICOM Gateway v2.1.0 New UI</h1>")

        with open(os.path.join(dev_dir, 'TTSG_DicomGateway.exe'), 'wb') as f:
            f.write(b"NEW_BINARY_DATA_V210")

        # 2. Tạo file patch .pkg
        pkg_file = os.path.join(dev_dir, 'TTSG_Gateway_Patch_v2.1.0.pkg')
        create_patch_package(
            version='2.1.0',
            release_notes='Cập nhật giao diện mới và sửa lỗi',
            source_dist_dir=dev_dir,
            output_pkg_path=pkg_file
        )
        assert os.path.exists(pkg_file)

        # 3. Giả lập thư mục cài đặt cũ trên máy khách hàng
        old_index = os.path.join(client_app_dir, 'templates', 'index.html')
        os.makedirs(os.path.dirname(old_index), exist_ok=True)
        with open(old_index, 'w', encoding='utf-8') as f:
            f.write("<h1>Old v2.0.0 UI</h1>")

        # 4. Khách hàng nạp và áp dụng patch
        res = verify_and_apply_patch(pkg_file, client_app_dir)
        assert res['success'] is True
        assert res['version'] == '2.1.0'
        assert res['updated_files_count'] >= 2

        # 5. Kiểm tra file trên máy khách đã được cập nhật
        with open(old_index, 'r', encoding='utf-8') as f:
            assert "v2.1.0 New UI" in f.read()

        with open(os.path.join(client_app_dir, 'TTSG_DicomGateway.exe'), 'rb') as f:
            assert f.read() == b"NEW_BINARY_DATA_V210"


def test_patch_protects_config_and_data():
    with tempfile.TemporaryDirectory() as dev_dir, tempfile.TemporaryDirectory() as client_app_dir:
        # File nhạy cảm trên máy khách
        cust_config = os.path.join(client_app_dir, 'config.yaml')
        with open(cust_config, 'w', encoding='utf-8') as f:
            f.write("pacs: {ip: '10.0.0.1', called_ae_title: 'HOSPITAL_PACS'}")

        # Thư mục build có chứa config mẫu
        with open(os.path.join(dev_dir, 'config.yaml'), 'w', encoding='utf-8') as f:
            f.write("pacs: {ip: '127.0.0.1', called_ae_title: 'SAMPLE_PACS'}")

        with open(os.path.join(dev_dir, 'run_server.bat'), 'w', encoding='utf-8') as f:
            f.write("@echo off\nrun")

        pkg_file = os.path.join(dev_dir, 'patch.pkg')
        create_patch_package('2.1.0', 'Test notes', dev_dir, pkg_file)

        res = verify_and_apply_patch(pkg_file, client_app_dir)
        assert res['success'] is True

        # Đảm bảo config của khách hàng không bị ghi đè!
        with open(cust_config, 'r', encoding='utf-8') as f:
            content = f.read()
            assert "HOSPITAL_PACS" in content
            assert "SAMPLE_PACS" not in content


def test_tampered_patch_rejected():
    with tempfile.TemporaryDirectory() as dev_dir, tempfile.TemporaryDirectory() as client_app_dir:
        with open(os.path.join(dev_dir, 'TTSG_DicomGateway.exe'), 'wb') as f:
            f.write(b"ORIGINAL_EXE")

        pkg_file = os.path.join(dev_dir, 'patch.pkg')
        create_patch_package('2.1.0', 'Test', dev_dir, pkg_file)

        # Giả mạo nội dung binary trong file zip mà không ký lại
        tampered_pkg = os.path.join(dev_dir, 'tampered.pkg')
        with zipfile.ZipFile(pkg_file, 'r') as zin, zipfile.ZipFile(tampered_pkg, 'w') as zout:
            for item in zin.infolist():
                if item.filename == 'payload/TTSG_DicomGateway.exe':
                    zout.writestr(item, b"MALICIOUS_HACKED_EXE")
                else:
                    zout.writestr(item, zin.read(item.filename))

        res = verify_and_apply_patch(tampered_pkg, client_app_dir)
        assert res['success'] is False
        assert "không khớp" in res['message'] or "không hợp lệ" in res['message']


def test_api_system_update_patch_endpoint():
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_path = os.path.join(tmp_dir, 'config.yaml')
        config = {
            'auth': {
                'enabled': True,
                'users': [
                    {'username': 'trind', 'password_hash': hash_password('admin123'), 'full_name': 'Super Admin', 'role': 'ADMIN', 'allowed_modalities': ['*']}
                ]
            },
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
            'watcher': {'watch_folders': [], 'stability_check_interval_sec': 1, 'stability_check_count': 2},
            'paths': {
                'dicom_staging_folder': os.path.join(tmp_dir, 'staging'),
                'processed_folder': os.path.join(tmp_dir, 'processed'),
                'failed_folder': os.path.join(tmp_dir, 'failed'),
                'duplicates_folder': os.path.join(tmp_dir, 'duplicates'),
                'retry_queue_folder': os.path.join(tmp_dir, 'queue'),
                'registry_db': os.path.join(tmp_dir, 'registry.sqlite3'),
            },
            'filename_pattern': {'regex': r'^(?P<patient_id>[A-Za-z0-9]+)', 'date_format': '%Y%m%d'},
            'metadata': {'default_value': 'UNKNOWN'},
            'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300], 'max_attempts': 3},
            'logging': {'log_folder': tmp_dir, 'level': 'INFO', 'retention_days': 90},
        }
        init_web_app(config, cfg_path, None, None, 1000)
        client = app.test_client()

        # Tạo file patch
        dev_dir = os.path.join(tmp_dir, 'dev')
        os.makedirs(dev_dir, exist_ok=True)
        with open(os.path.join(dev_dir, 'run_server.bat'), 'w', encoding='utf-8') as f:
            f.write("@echo off\nrun_new")

        pkg_path = os.path.join(tmp_dir, 'patch.pkg')
        create_patch_package('2.1.0', 'Release update', dev_dir, pkg_path)

        with open(pkg_path, 'rb') as f:
            pkg_bytes = f.read()

        # 1. Chưa đăng nhập -> 401
        res_no_auth = client.post(
            '/api/system/update-patch',
            data={'file': (io.BytesIO(pkg_bytes), 'patch.pkg')},
            content_type='multipart/form-data'
        )
        assert res_no_auth.status_code == 401

        # 2. Đăng nhập Admin
        client.post('/api/auth/login', json={'username': 'trind', 'password': 'admin123'})

        # 3. Nạp file patch thành công
        res_auth = client.post(
            '/api/system/update-patch',
            data={'file': (io.BytesIO(pkg_bytes), 'patch.pkg')},
            content_type='multipart/form-data'
        )
        assert res_auth.status_code == 200
        data = res_auth.get_json()
        assert data['success'] is True
        assert data['version'] == '2.1.0'

import io
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402

from web_server import app, init_web_app  # noqa: E402


def test_api_upload_manual_no_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            'paths': {
                'dicom_staging_folder': os.path.join(tmp_dir, 'staging'),
                'processed_folder': os.path.join(tmp_dir, 'processed'),
                'failed_folder': os.path.join(tmp_dir, 'failed'),
            },
            'filename_pattern': {
                'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
                'date_format': '%Y%m%d',
            },
            'metadata': {'default_value': 'UNKNOWN'},
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
        }
        init_web_app(config, 'config.yaml', None, None, 1000)
        client = app.test_client()

        res = client.post('/api/upload-manual')
        assert res.status_code == 400
        data = res.get_json()
        assert data['success'] is False


def test_api_upload_manual_success():
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            'paths': {
                'dicom_staging_folder': os.path.join(tmp_dir, 'staging'),
                'processed_folder': os.path.join(tmp_dir, 'processed'),
                'failed_folder': os.path.join(tmp_dir, 'failed'),
            },
            'filename_pattern': {
                'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
                'date_format': '%Y%m%d',
            },
            'metadata': {'default_value': 'UNKNOWN'},
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
        }
        init_web_app(config, 'config.yaml', None, None, 1000)
        client = app.test_client()

        # Create dummy PNG image in memory
        img_bytes = io.BytesIO()
        Image.new('RGB', (10, 10), color='white').save(img_bytes, format='PNG')
        img_bytes.seek(0)

        with patch('web_server.DicomSender') as MockSender:
            mock_instance = MagicMock()
            mock_instance.send.return_value = (True, None)
            MockSender.return_value = mock_instance

            res = client.post(
                '/api/upload-manual',
                data={
                    'files': (img_bytes, 'BN001_NguyenVanA_20260811.png'),
                    'patient_id': 'BN001',
                    'patient_name': 'NguyenVanA',
                    'study_description': 'Sieu am o bung tong quat',
                    'modality': 'US',
                },
                content_type='multipart/form-data',
            )

            assert res.status_code == 200
            data = res.get_json()
            assert data['success'] is True
            assert len(data['results']) == 1
            assert data['results'][0]['success'] is True
            assert 'SOPInstanceUID' in data['results'][0]['message']


def test_api_upload_manual_study_instance_uid_batch():
    import pydicom
    with tempfile.TemporaryDirectory() as tmp_dir:
        staging_dir = os.path.join(tmp_dir, 'staging')
        config = {
            'paths': {
                'dicom_staging_folder': staging_dir,
                'processed_folder': os.path.join(tmp_dir, 'processed'),
                'failed_folder': os.path.join(tmp_dir, 'failed'),
            },
            'filename_pattern': {
                'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
                'date_format': '%Y%m%d',
            },
            'metadata': {'default_value': 'UNKNOWN'},
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
        }
        init_web_app(config, 'config.yaml', None, None, 1000)
        client = app.test_client()

        img_bytes1 = io.BytesIO()
        Image.new('RGB', (10, 10), color='white').save(img_bytes1, format='PNG')
        img_bytes1.seek(0)

        img_bytes2 = io.BytesIO()
        Image.new('RGB', (10, 10), color='blue').save(img_bytes2, format='PNG')
        img_bytes2.seek(0)

        expected_study_uid = '1.2.840.113619.2.55.3.2831158860.678'

        with patch('web_server.DicomSender') as MockSender:
            mock_instance = MagicMock()
            sent_dicom_files = []
            def fake_send(dicom_path):
                sent_dicom_files.append(dicom_path)
                return True, None
            mock_instance.send.side_effect = fake_send
            MockSender.return_value = mock_instance

            res = client.post(
                '/api/upload-manual',
                data={
                    'files': [(img_bytes1, 'img1.png'), (img_bytes2, 'img2.png')],
                    'patient_id': 'BN18000991',
                    'patient_name': 'ADMIN TEST1',
                    'accession_number': '3040784',
                    'study_instance_uid': expected_study_uid,
                    'study_description': 'Sieu am o bung',
                    'modality': 'US',
                },
                content_type='multipart/form-data',
            )

            assert res.status_code == 200
            data = res.get_json()
            assert data['success'] is True
            assert len(sent_dicom_files) == 2

            ds1 = pydicom.dcmread(sent_dicom_files[0])
            ds2 = pydicom.dcmread(sent_dicom_files[1])

            assert ds1.PatientID == 'BN18000991'
            assert ds2.PatientID == 'BN18000991'
            assert ds1.AccessionNumber == '3040784'
            assert ds2.AccessionNumber == '3040784'
            assert ds1.StudyInstanceUID == expected_study_uid
            assert ds2.StudyInstanceUID == expected_study_uid
            assert ds1.InstanceNumber == '1'
            assert ds2.InstanceNumber == '2'


def test_api_modalities_summary():
    from utils import ProcessedRegistry
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, 'registry.sqlite3')
        registry = ProcessedRegistry(db_path)
        try:
            registry.record_study('us.png', {'patient_id': 'BN01', 'modality': 'US'}, 'SUCCESS')
            registry.record_study('es.png', {'patient_id': 'BN02', 'modality': 'ES'}, 'RETRYING')

            config = {
                'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
                'ris': {'enabled': False},
                'watcher': {
                    'watch_folders': [
                        {'path': './data/inbox_us', 'modality': 'US'},
                        {'path': './data/inbox_es', 'modality': 'ES'},
                    ]
                }
            }
            init_web_app(config, 'config.yaml', None, None, 1000, registry)
            client = app.test_client()

            res = client.get('/api/modalities/summary')
            assert res.status_code == 200
            data = res.get_json()
            assert data['success'] is True
            assert 'summary' in data
            assert data['summary']['total_studies_today'] == 2
            assert data['summary']['success_studies_today'] == 1
            assert data['summary']['retrying_studies_today'] == 1

            modalities = data['modalities']
            us_mod = next((m for m in modalities if m['code'] == 'US'), None)
            assert us_mod is not None
            assert us_mod['status'] == 'ACTIVE'
            assert us_mod['stats_today']['success'] == 1
            assert us_mod['is_configured'] is True

            es_mod = next((m for m in modalities if m['code'] == 'ES'), None)
            assert es_mod is not None
            assert es_mod['stats_today']['retrying'] == 1
        finally:
            registry.close()


def test_auth_login_and_logout():
    from utils import hash_password
    with tempfile.TemporaryDirectory() as tmp_dir:
        config = {
            'auth': {
                'enabled': True,
                'secret_key': 'test_secret_123',
                'users': [
                    {
                        'username': 'trind',
                        'password_hash': hash_password('dinhtri87'),
                        'full_name': 'Nguyễn Đình Trí',
                        'department': 'Công nghệ thông tin',
                        'role': 'ADMIN',
                        'allowed_modalities': ['*'],
                    },
                    {
                        'username': 'ktv_us',
                        'password_hash': hash_password('123456'),
                        'full_name': 'KTV Sieu Am',
                        'department': 'Khoa CĐHA',
                        'role': 'TECHNICIAN',
                        'allowed_modalities': ['US'],
                    }
                ]
            },
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
            'paths': {'processed_folder': './processed', 'failed_folder': './failed'},
            'logging': {'log_folder': tmp_dir},
        }
        init_web_app(config, os.path.join(tmp_dir, 'config.yaml'), None, None, 1000)
        client = app.test_client()

        # Login with wrong credentials -> 401
        res = client.post('/api/auth/login', json={'username': 'trind', 'password': 'wrongpassword'})
        assert res.status_code == 401
        assert res.get_json()['success'] is False

        # Login with correct admin credentials -> 200
        res = client.post('/api/auth/login', json={'username': 'trind', 'password': 'dinhtri87'})
        assert res.status_code == 200
        assert res.get_json()['success'] is True
        assert res.get_json()['user']['role'] == 'ADMIN'
        assert res.get_json()['user']['full_name'] == 'Nguyễn Đình Trí'
        assert res.get_json()['user']['department'] == 'Công nghệ thông tin'

        # Check /api/auth/me
        me = client.get('/api/auth/me')
        assert me.status_code == 200
        assert me.get_json()['user']['username'] == 'trind'
        assert me.get_json()['user']['department'] == 'Công nghệ thông tin'

        # Logout
        logout_res = client.post('/api/auth/logout')
        assert logout_res.status_code == 200

        # After logout, me -> 401
        me_after = client.get('/api/auth/me')
        assert me_after.status_code == 401


def test_rbac_technician_blocked_from_admin_apis():
    from utils import hash_password
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_file = os.path.join(tmp_dir, 'config.yaml')
        config = {
            'auth': {
                'enabled': True,
                'secret_key': 'test_secret_123',
                'users': [
                    {
                        'username': 'admin',
                        'password_hash': hash_password('admin123'),
                        'full_name': 'Super Admin',
                        'role': 'ADMIN',
                        'allowed_modalities': ['*'],
                    },
                    {
                        'username': 'ktv_us',
                        'password_hash': hash_password('123456'),
                        'full_name': 'KTV Sieu Am',
                        'role': 'TECHNICIAN',
                        'allowed_modalities': ['US'],
                    }
                ]
            },
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
            'paths': {'processed_folder': './processed', 'failed_folder': './failed'},
            'logging': {'log_folder': tmp_dir},
        }
        init_web_app(config, cfg_file, None, None, 1000)
        client = app.test_client()

        # Login as Technician
        client.post('/api/auth/login', json={'username': 'ktv_us', 'password': '123456'})

        # Technician trying to access /api/config -> 403 Forbidden
        cfg_res = client.get('/api/config')
        assert cfg_res.status_code == 403

        # Technician trying to access /api/logs -> 403 Forbidden
        log_res = client.get('/api/logs')
        assert log_res.status_code == 403

        # Technician trying to list users -> 403 Forbidden
        user_res = client.get('/api/admin/users')
        assert user_res.status_code == 403

        # Now login as Admin
        client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin123'})

        # Admin CAN access /api/config
        assert client.get('/api/config').status_code == 200
        # Admin CAN access /api/logs
        assert client.get('/api/logs').status_code == 200
        # Admin CAN access /api/admin/users
        assert client.get('/api/admin/users').status_code == 200


def test_modality_data_isolation_for_technician():
    from utils import ProcessedRegistry, hash_password
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, 'registry.sqlite3')
        registry = ProcessedRegistry(db_path)
        try:
            registry.record_study('us_01.png', {'patient_id': 'BN_US', 'modality': 'US', 'patient_name': 'Nguyen US'}, 'SUCCESS')
            registry.record_study('ct_01.png', {'patient_id': 'BN_CT', 'modality': 'CT', 'patient_name': 'Tran CT'}, 'SUCCESS')

            config = {
                'auth': {
                    'enabled': True,
                    'secret_key': 'test_secret_123',
                    'users': [
                        {
                            'username': 'admin',
                            'password_hash': hash_password('admin123'),
                            'role': 'ADMIN',
                            'allowed_modalities': ['*'],
                        },
                        {
                            'username': 'ktv_us',
                            'password_hash': hash_password('123456'),
                            'role': 'TECHNICIAN',
                            'allowed_modalities': ['US'],
                        }
                    ]
                },
                'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
                'ris': {'enabled': False},
                'paths': {'processed_folder': './processed', 'failed_folder': './failed'},
                'logging': {'log_folder': tmp_dir},
            }
            init_web_app(config, os.path.join(tmp_dir, 'config.yaml'), None, None, 1000, registry)
            client = app.test_client()

            # 1. Admin sees both US and CT
            client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin123'})
            res_admin = client.get('/api/studies')
            studies_admin = res_admin.get_json()['studies']
            assert len(studies_admin) == 2

            # 2. Technician (US) ONLY sees US
            client.post('/api/auth/login', json={'username': 'ktv_us', 'password': '123456'})
            res_ktv = client.get('/api/studies')
            studies_ktv = res_ktv.get_json()['studies']
            assert len(studies_ktv) == 1
            assert studies_ktv[0]['modality'] == 'US'
            assert studies_ktv[0]['patient_id'] == 'BN_US'
        finally:
            registry.close()


def test_admin_user_management_with_department():
    from utils import hash_password
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_file = os.path.join(tmp_dir, 'config.yaml')
        config = {
            'auth': {
                'enabled': True,
                'secret_key': 'test_secret_123',
                'users': [
                    {
                        'username': 'trind',
                        'password_hash': hash_password('dinhtri87'),
                        'full_name': 'Nguyễn Đình Trí',
                        'department': 'Công nghệ thông tin',
                        'role': 'ADMIN',
                        'allowed_modalities': ['*'],
                    }
                ]
            },
            'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
            'ris': {'enabled': False},
            'watcher': {
                'watch_folders': [{'path': os.path.join(tmp_dir, 'inbox'), 'modality': 'US'}],
                'stability_check_interval_sec': 1,
                'stability_check_count': 2,
            },
            'paths': {
                'dicom_staging_folder': os.path.join(tmp_dir, 'staging'),
                'processed_folder': os.path.join(tmp_dir, 'processed'),
                'failed_folder': os.path.join(tmp_dir, 'failed'),
                'duplicates_folder': os.path.join(tmp_dir, 'duplicates'),
                'retry_queue_folder': os.path.join(tmp_dir, 'queue'),
                'registry_db': os.path.join(tmp_dir, 'registry.sqlite3'),
            },
            'filename_pattern': {
                'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
                'date_format': '%Y%m%d',
            },
            'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
            'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300, 600], 'max_attempts': 3},
            'logging': {'log_folder': tmp_dir, 'level': 'INFO', 'retention_days': 90},
        }
        init_web_app(config, cfg_file, None, None, 1000)
        client = app.test_client()

        # Login as Admin
        client.post('/api/auth/login', json={'username': 'trind', 'password': 'dinhtri87'})

        # List users
        users_res = client.get('/api/admin/users')
        assert users_res.status_code == 200
        users = users_res.get_json()['users']
        assert len(users) == 1
        assert users[0]['username'] == 'trind'
        assert users[0]['department'] == 'Công nghệ thông tin'

        # Add new user with department
        add_res = client.post('/api/admin/users', json={
            'username': 'ktv_es',
            'full_name': 'KTV Nội Soi',
            'department': 'Khoa Thăm dò chức năng',
            'role': 'TECHNICIAN',
            'allowed_modalities': ['ES'],
            'password': 'password123'
        })
        assert add_res.status_code == 200
        assert add_res.get_json()['user']['department'] == 'Khoa Thăm dò chức năng'

        # Verify in list
        users_res2 = client.get('/api/admin/users')
        users2 = users_res2.get_json()['users']
        assert len(users2) == 2
        es_user = next(u for u in users2 if u['username'] == 'ktv_es')
        assert es_user['department'] == 'Khoa Thăm dò chức năng'





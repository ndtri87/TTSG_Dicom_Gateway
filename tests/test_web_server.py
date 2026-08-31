import io
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image  # noqa: E402
from utils import hash_password  # noqa: E402
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

            with open(sent_dicom_files[0], 'rb') as f1:
                ds1 = pydicom.dcmread(f1)
                assert ds1.PatientID == 'BN18000991'
                assert ds1.AccessionNumber == '3040784'
                assert ds1.StudyInstanceUID == expected_study_uid
                assert ds1.InstanceNumber == '1'

            with open(sent_dicom_files[1], 'rb') as f2:
                ds2 = pydicom.dcmread(f2)
                assert ds2.PatientID == 'BN18000991'
                assert ds2.AccessionNumber == '3040784'
                assert ds2.StudyInstanceUID == expected_study_uid
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


def test_api_worklist_filter_status():
    from utils import ProcessedRegistry
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, 'registry.sqlite3')
        registry = ProcessedRegistry(db_path)
        try:
            # Ghi nhận 1 ca đã hoàn thành ACC101
            registry.record_study(
                'us.png',
                {'patient_id': 'BN01', 'patient_name': 'Nguyen A', 'accession_number': 'ACC101', 'modality': 'US'},
                'SUCCESS',
                sop_instance_uid='1.2.3.4.99'
            )

            config = {
                'paths': {
                    'dicom_staging_folder': os.path.join(tmp_dir, 'staging'),
                    'processed_folder': os.path.join(tmp_dir, 'processed'),
                    'failed_folder': os.path.join(tmp_dir, 'failed'),
                    'registry_db': db_path,
                },
                'filename_pattern': {
                    'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
                    'date_format': '%Y%m%d',
                },
                'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
                'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
                'ris': {'enabled': True, 'ip': '127.0.0.1', 'port': 6003, 'called_ae_title': 'RIS', 'calling_ae_title': 'GATEWAY'},
            }
            init_web_app(config, 'config.yaml', None, None, 1000, registry=registry)
            client = app.test_client()

            # Mock WorklistClient.query_worklist returning 2 items (ACC101 - completed, ACC102 - pending)
            mock_items = [
                {'patient_id': 'BN01', 'patient_name': 'Nguyen A', 'accession_number': 'ACC101', 'modality': 'US', 'study_description': 'Sieu am'},
                {'patient_id': 'BN02', 'patient_name': 'Tran B', 'accession_number': 'ACC102', 'modality': 'US', 'study_description': 'Sieu am'},
            ]

            with patch('web_server.WorklistClient') as MockClient:
                mock_inst = MagicMock()
                mock_inst.query_worklist.return_value = mock_items
                MockClient.return_value = mock_inst

                # 1. Test default / status=PENDING (Chỉ trả về ca chưa làm)
                res_pending = client.get('/api/worklist?status=PENDING')
                assert res_pending.status_code == 200
                data_pending = res_pending.get_json()
                assert data_pending['success'] is True
                assert len(data_pending['items']) == 1
                assert data_pending['items'][0]['accession_number'] == 'ACC102'
                assert data_pending['counts']['pending'] == 1
                assert data_pending['counts']['completed'] == 1
                assert data_pending['counts']['total'] == 2

                # 2. Test status=COMPLETED (Chỉ trả về ca đã đẩy PACS)
                res_completed = client.get('/api/worklist?status=COMPLETED')
                assert res_completed.status_code == 200
                data_completed = res_completed.get_json()
                assert len(data_completed['items']) == 1
                assert data_completed['items'][0]['accession_number'] == 'ACC101'
                assert data_completed['items'][0]['is_completed'] is True

                # 3. Test status=ALL (Trả về tất cả kèm cờ is_completed)
                res_all = client.get('/api/worklist?status=ALL')
                assert res_all.status_code == 200
                data_all = res_all.get_json()
                assert len(data_all['items']) == 2
        finally:
            registry.close()


def test_station_authentication_and_rbac():
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
            'stations': [
                {'id': 'US_01', 'name': 'Phòng Siêu âm 01', 'department': 'Khoa CĐHA', 'allowed_modalities': ['US'], 'default_modality': 'US', 'icon': '🩺'}
            ]
        }
        init_web_app(config, cfg_path, None, None, 1000)
        client = app.test_client()

        # 1. GET /api/stations công khai
        res_stations = client.get('/api/stations')
        assert res_stations.status_code == 200
        st_data = res_stations.get_json()
        assert st_data['success'] is True
        assert len(st_data['stations']) >= 1
        assert st_data['stations'][0]['id'] == 'US_01'

        # 2. Đăng nhập Station không cần mật khẩu
        res_login = client.post('/api/auth/station-login', json={
            'station_id': 'US_01',
            'technician_name': 'KTV Tran Van B',
            'remember': True
        })
        assert res_login.status_code == 200
        login_data = res_login.get_json()
        assert login_data['success'] is True
        assert login_data['user']['is_station'] is True
        assert login_data['user']['station_id'] == 'US_01'
        assert login_data['user']['technician_name'] == 'KTV Tran Van B'
        assert login_data['user']['role'] == 'TECHNICIAN'
        assert login_data['user']['allowed_modalities'] == ['US']

        # 3. GET /api/auth/me trả về thông tin station
        res_me = client.get('/api/auth/me')
        assert res_me.status_code == 200
        me_data = res_me.get_json()
        assert me_data['user']['is_station'] is True
        assert me_data['user']['station_id'] == 'US_01'

        # 4. Station role bị chặn truy cập API Admin
        res_admin_users = client.get('/api/admin/users')
        assert res_admin_users.status_code == 403
        res_admin_stations = client.get('/api/admin/stations')
        assert res_admin_stations.status_code == 403

        # 5. Station không được đổi mật khẩu
        res_change_pwd = client.post('/api/auth/change-password', json={'old_password': '1', 'new_password': '2'})
        assert res_change_pwd.status_code == 400


def test_admin_station_management():
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
            'stations': [
                {'id': 'US_01', 'name': 'Phòng Siêu âm 01', 'department': 'Khoa CĐHA', 'allowed_modalities': ['US'], 'default_modality': 'US', 'icon': '🩺'}
            ]
        }
        init_web_app(config, cfg_path, None, None, 1000)
        client = app.test_client()

        # Đăng nhập Admin bằng mật khẩu
        client.post('/api/auth/login', json={'username': 'trind', 'password': 'admin123'})

        # 1. Admin lấy danh sách trạm
        res_list = client.get('/api/admin/stations')
        assert res_list.status_code == 200
        assert len(res_list.get_json()['stations']) == 1

        # 2. Admin thêm trạm mới
        res_add = client.post('/api/admin/stations', json={
            'id': 'ES_01',
            'name': 'Phòng Nội Soi 01',
            'department': 'Khoa TDCN',
            'icon': '🔬',
            'allowed_modalities': ['ES']
        })
        assert res_add.status_code == 200
        assert res_add.get_json()['station']['id'] == 'ES_01'

        # 3. Admin xóa trạm
        res_del = client.delete('/api/admin/stations/ES_01')
        assert res_del.status_code == 200
        assert res_del.get_json()['success'] is True


def test_auth_brute_force_lockout():
    from web_server import auth_rate_limiter
    auth_rate_limiter._records.clear()

    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_path = os.path.join(tmp_dir, 'config.yaml')
        config = {
            'auth': {
                'enabled': True,
                'users': [
                    {'username': 'trind', 'password_hash': hash_password('correct_pwd'), 'full_name': 'Super Admin', 'role': 'ADMIN', 'allowed_modalities': ['*']}
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
            'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
            'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300], 'max_attempts': 3},
            'logging': {'log_folder': tmp_dir, 'level': 'INFO', 'retention_days': 90},
        }
        init_web_app(config, cfg_path, None, None, 1000)
        client = app.test_client()

        # 4 lần gõ sai đầu tiên trả về 401
        for i in range(4):
            res = client.post('/api/auth/login', json={'username': 'trind', 'password': f'wrong_{i}'})
            assert res.status_code == 401
            assert res.get_json()['success'] is False

        # Lần gõ sai thứ 5 -> kích hoạt khóa 429
        res5 = client.post('/api/auth/login', json={'username': 'trind', 'password': 'wrong_5'})
        assert res5.status_code == 429
        data5 = res5.get_json()
        assert data5['code'] == 'LOCKED_OUT'
        assert data5['lockout_remaining'] > 0

        # Lần thứ 6 dù gõ đúng mật khẩu vẫn bị chặn 429 vì đang trong thời gian khóa
        res6 = client.post('/api/auth/login', json={'username': 'trind', 'password': 'correct_pwd'})
        assert res6.status_code == 429
        assert res6.get_json()['code'] == 'LOCKED_OUT'


def test_api_license_endpoints():
    from license_generator import generate_license_data
    from license_manager import get_machine_fingerprint

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
            'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
            'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300], 'max_attempts': 3},
            'logging': {'log_folder': tmp_dir, 'level': 'INFO', 'retention_days': 90},
        }
        init_web_app(config, cfg_path, None, None, 1000)
        client = app.test_client()

        # 1. Kiểm tra trạng thái License ban đầu (Mặc định DEMO)
        res_status = client.get('/api/license/status')
        assert res_status.status_code == 200
        lic_init = res_status.get_json()['license']
        assert lic_init['status'] == 'DEMO'
        assert lic_init['hardware_id'].startswith('TTSG-')

        # 2. Đăng nhập Admin để kích hoạt
        client.post('/api/auth/login', json={'username': 'trind', 'password': 'admin123'})

        # 3. Kích hoạt License hợp lệ
        hwid = get_machine_fingerprint()
        lic_payload = generate_license_data(
            customer_name='Bệnh viện Đa khoa Tâm Trí Sài Gòn',
            hardware_id=hwid,
            expiration_date='2035-12-31',
            allowed_modalities=['US', 'ES', 'ECG'],
            max_stations=30,
            plan_name='Enterprise Medical Edition'
        )

        res_act = client.post('/api/license/activate', json={'license_key': lic_payload})
        assert res_act.status_code == 200
        act_data = res_act.get_json()
        assert act_data['success'] is True
        assert act_data['license']['status'] == 'VALID'
        assert act_data['license']['customer_name'] == 'Bệnh viện Đa khoa Tâm Trí Sài Gòn'

        # 4. Kiểm tra lại qua GET /api/license/status
        res_check = client.get('/api/license/status')
        assert res_check.get_json()['license']['status'] == 'VALID'









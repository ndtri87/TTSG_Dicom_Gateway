"""Client Agent xác thực bằng mã trạm, tài khoản admin ban đầu, và thực thi bản quyền."""
import io
import json
import os
from datetime import date, timedelta
from unittest.mock import patch

import pytest
import yaml
from PIL import Image

from license_generator import generate_license_data
from license_manager import LicenseManager, get_machine_fingerprint
from utils import ensure_bootstrap_admin, hash_password, upsert_user
from web_server import app, init_web_app


def _config(tmp_path):
    return {
        'auth': {
            'enabled': True,
            'users': [{'username': 'admin', 'password_hash': hash_password('admin-pass'), 'role': 'ADMIN',
                       'full_name': 'Admin', 'allowed_modalities': ['*']}],
        },
        'stations': [
            {'id': 'US_01', 'name': 'Phòng Siêu âm 01', 'allowed_modalities': ['US'], 'default_modality': 'US'},
            {'id': 'ES_01', 'name': 'Phòng Nội soi', 'allowed_modalities': ['ES'], 'default_modality': 'ES'},
        ],
        'pacs': {'ip': '127.0.0.1', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
        'ris': {'enabled': False},
        'watcher': {'watch_folders': [{'path': str(tmp_path / 'inbox'), 'modality': 'US'}],
                    'stability_check_interval_sec': 1, 'stability_check_count': 2},
        'paths': {k: str(tmp_path / k) for k in ('dicom_staging_folder', 'processed_folder', 'failed_folder',
                                                  'duplicates_folder', 'retry_queue_folder')}
                 | {'registry_db': str(tmp_path / 'registry.sqlite3')},
        'filename_pattern': {'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
                             'date_format': '%Y%m%d'},
        'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
        'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300], 'max_attempts': 3},
        'logging': {'log_folder': str(tmp_path), 'level': 'INFO', 'retention_days': 90},
    }


def _png():
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), color='white').save(buf, format='PNG')
    buf.seek(0)
    return buf


def _write_license(path, modalities=('*',), exp=None, max_stations=50):
    exp = exp or (date.today() + timedelta(days=365)).strftime('%Y-%m-%d')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(generate_license_data('BV Test', get_machine_fingerprint(), exp, list(modalities), max_stations))


@pytest.fixture
def admin_client(tmp_path):
    cfg_path = str(tmp_path / 'config.yaml')
    config = _config(tmp_path)
    with open(cfg_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    init_web_app(config, cfg_path, None, None, 1000)
    client = app.test_client()
    client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin-pass'})
    return client, config


def test_station_key_lets_client_agent_upload(admin_client):
    client, _ = admin_client
    res = client.post('/api/admin/stations/US_01/api-key')
    assert res.status_code == 200
    key = res.get_json()['api_key']
    assert key.startswith('ttsg_') and len(key) > 20

    # Danh sách công khai (màn hình login) không được lộ mã
    public = client.get('/api/stations').get_json()['stations']
    assert all('api_key' not in s for s in public)
    admin_list = client.get('/api/admin/stations').get_json()['stations']
    assert next(s for s in admin_list if s['id'] == 'US_01')['api_key'] == key

    agent = app.test_client()  # không có session đăng nhập
    with patch('web_server.DicomSender') as MockSender:
        MockSender.return_value.send.return_value = (True, None)
        ok = agent.post('/api/upload-manual', data={'files': (_png(), 'BN001_NguyenVanA_20260811.png')},
                        headers={'X-Station-Key': key}, content_type='multipart/form-data')
        bad = agent.post('/api/upload-manual', data={'files': (_png(), 'BN001_NguyenVanA_20260811.png')},
                         headers={'X-Station-Key': 'ttsg_wrong_key_wrong_key_xx'}, content_type='multipart/form-data')
        anon = agent.post('/api/upload-manual', data={'files': (_png(), 'BN001_NguyenVanA_20260811.png')},
                          content_type='multipart/form-data')

    assert ok.status_code == 200 and ok.get_json()['success'] is True
    assert bad.status_code == 401
    assert anon.status_code == 401


def test_station_key_is_scoped_to_station_modality(admin_client):
    client, _ = admin_client
    key = client.post('/api/admin/stations/US_01/api-key').get_json()['api_key']
    agent = app.test_client()
    res = agent.post('/api/upload-manual', data={'files': (_png(), 'a.png'), 'modality': 'ES'},
                     headers={'X-Station-Key': key}, content_type='multipart/form-data')
    assert res.status_code == 403


def test_regenerated_station_key_revokes_old_one(admin_client):
    client, _ = admin_client
    old = client.post('/api/admin/stations/US_01/api-key').get_json()['api_key']
    new = client.post('/api/admin/stations/US_01/api-key').get_json()['api_key']
    assert old != new
    agent = app.test_client()
    assert agent.get('/api/auth/me', headers={'X-Station-Key': old}).status_code == 401
    assert agent.get('/api/auth/me', headers={'X-Station-Key': new}).status_code == 200


def test_upload_rejected_when_trial_expired(admin_client, isolated_web_data_dir):
    client, config = admin_client
    with open(isolated_web_data_dir / '.trial.json', 'w', encoding='utf-8') as f:
        json.dump({'installed_at': (date.today() - timedelta(days=40)).isoformat(), 'trial_days': 30}, f)
    init_web_app(config, config_path_of(client), None, None, 1000)

    with patch('web_server.DicomSender') as MockSender:
        res = client.post('/api/upload-manual', data={'files': (_png(), 'a.png'), 'modality': 'US'},
                          content_type='multipart/form-data')
        MockSender.return_value.send.assert_not_called()
    result = res.get_json()['results'][0]
    assert result['success'] is False and result['license_error'] is True


def test_upload_rejected_for_unlicensed_modality(admin_client, isolated_web_data_dir):
    client, config = admin_client
    _write_license(isolated_web_data_dir / 'license.key', modalities=('US',))
    init_web_app(config, config_path_of(client), None, None, 1000)

    with patch('web_server.DicomSender') as MockSender:
        MockSender.return_value.send.return_value = (True, None)
        us = client.post('/api/upload-manual', data={'files': (_png(), 'a.png'), 'modality': 'US'},
                         content_type='multipart/form-data').get_json()
        es = client.post('/api/upload-manual', data={'files': (_png(), 'b.png'), 'modality': 'ES'},
                         content_type='multipart/form-data').get_json()
    assert us['results'][0]['success'] is True
    assert es['results'][0]['success'] is False and es['results'][0]['license_error'] is True


def test_station_count_limited_by_license(admin_client, isolated_web_data_dir):
    client, config = admin_client
    _write_license(isolated_web_data_dir / 'license.key', max_stations=2)
    init_web_app(config, config_path_of(client), None, None, 1000)
    res = client.post('/api/admin/stations', json={'id': 'NEW_01', 'name': 'Phòng mới', 'allowed_modalities': ['US']})
    assert res.status_code == 403
    # Sửa trạm đã có vẫn được phép
    res = client.post('/api/admin/stations', json={'id': 'US_01', 'name': 'Phòng Siêu âm 01 (đổi tên)'})
    assert res.status_code == 200


def test_license_manager_check_processing_allowed(tmp_path):
    lic = tmp_path / 'license.key'
    _write_license(lic, modalities=('US', 'ES'))
    lm = LicenseManager(license_path=str(lic))
    assert lm.check_processing_allowed('US') == (True, '')
    ok, reason = lm.check_processing_allowed('CT')
    assert ok is False and 'CT' in reason


def test_bootstrap_admin_created_once(tmp_path):
    cfg_path = str(tmp_path / 'config.yaml')
    config = _config(tmp_path)
    config['auth']['users'] = []
    pwd = ensure_bootstrap_admin(config, cfg_path, str(tmp_path / 'data'))
    assert pwd and len(pwd) >= 10
    assert config['auth']['users'][0]['username'] == 'admin'
    pwd_file = tmp_path / 'data' / 'initial_admin_password.txt'
    assert pwd in pwd_file.read_text(encoding='utf-8')
    with open(cfg_path, encoding='utf-8') as f:
        assert yaml.safe_load(f)['auth']['users'][0]['username'] == 'admin'
    # Đã có tài khoản -> không tạo lại
    assert ensure_bootstrap_admin(config, cfg_path, str(tmp_path / 'data')) is None


def test_new_user_requires_password(tmp_path):
    config = _config(tmp_path)
    with pytest.raises(ValueError):
        upsert_user(config, str(tmp_path / 'config.yaml'), {'username': 'ktv_new', 'role': 'TECHNICIAN'})


def config_path_of(_client):
    import web_server
    return web_server.config_path


def test_invalid_license_status_has_complete_fields(tmp_path):
    """License sai máy / sai chữ ký: đủ trường để giao diện không hiện 'undefined' / 'NaN'."""
    lic = tmp_path / 'license.key'
    with open(lic, 'w', encoding='utf-8') as f:
        f.write(generate_license_data('BV Khác', 'TTSG-0000-0000-0000-0000', 'PERMANENT', ['*'], 10))
    status = LicenseManager(license_path=str(lic)).get_summary()
    assert status['status'] == 'HARDWARE_MISMATCH'
    for key in ('days_remaining', 'max_stations', 'allowed_modalities', 'expiration_date', 'plan_name'):
        assert key in status
    assert status['days_remaining'] == 0 and status['max_stations'] == 0

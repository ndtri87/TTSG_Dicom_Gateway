"""Đổi cấu hình -> báo/khởi động lại service; firewall mở đúng port trong config.yaml."""
import copy
import os
from unittest.mock import MagicMock, patch

import yaml

import utils
from utils import config_changes_require_restart, configure_firewall, get_firewall_ports, hash_password
from web_server import app, init_web_app


def _base_config(tmp_path):
    return {
        'auth': {'enabled': True, 'users': [{'username': 'admin', 'password_hash': hash_password('admin-pass'),
                                             'role': 'ADMIN', 'allowed_modalities': ['*']}]},
        'pacs': {'ip': '192.168.6.213', 'port': 6002, 'called_ae_title': 'PACS', 'calling_ae_title': 'GW',
                 'storage_commitment': {'enabled': True, 'listen_port': 105}},
        'ris': {'enabled': False},
        'web_ui': {'port': 5000},
        'watcher': {'watch_folders': [{'path': str(tmp_path / 'inbox'), 'modality': 'US'}],
                    'stability_check_interval_sec': 1, 'stability_check_count': 2},
        'paths': {k: str(tmp_path / k) for k in ('dicom_staging_folder', 'processed_folder', 'failed_folder',
                                                  'duplicates_folder', 'retry_queue_folder')}
                 | {'registry_db': str(tmp_path / 'registry.sqlite3')},
        'filename_pattern': {'regex': r'^(?P<patient_id>[A-Za-z0-9]+)', 'date_format': '%Y%m%d'},
        'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
        'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300], 'max_attempts': 3},
        'logging': {'log_folder': str(tmp_path), 'level': 'INFO', 'retention_days': 90},
    }


def test_config_changes_require_restart_detects_connection_sections(tmp_path):
    old = _base_config(tmp_path)
    new = copy.deepcopy(old)
    assert config_changes_require_restart(old, new) == []

    new['pacs']['ip'] = '10.0.0.9'
    new['web_ui']['port'] = 8080
    assert config_changes_require_restart(old, new) == ['pacs', 'web_ui']

    # Tài khoản / nơi thực hiện được đọc trực tiếp mỗi request -> không cần khởi động lại
    only_auth = copy.deepcopy(old)
    only_auth['auth']['session_lifetime_days'] = 7
    only_auth['stations'] = [{'id': 'X', 'name': 'X'}]
    assert config_changes_require_restart(old, only_auth) == []


def test_firewall_ports_follow_config(tmp_path):
    cfg = _base_config(tmp_path)
    assert get_firewall_ports(cfg) == (5000, 105)
    cfg['web_ui']['port'] = 8080
    cfg['pacs']['storage_commitment'] = {'enabled': False, 'listen_port': 105}
    assert get_firewall_ports(cfg) == (8080, None)


def test_configure_firewall_opens_configured_ports(tmp_path):
    cfg = _base_config(tmp_path)
    cfg['web_ui']['port'] = 8443
    cfg['pacs']['storage_commitment']['listen_port'] = 11105
    with patch.object(utils.os, 'name', 'nt'), patch('subprocess.run') as run:
        run.return_value = MagicMock(returncode=0)
        assert configure_firewall(cfg) is True
    cmds = [' '.join(c.args[0]) for c in run.call_args_list]
    assert any('delete rule' in c and 'Web UI' in c for c in cmds)
    assert any('add rule' in c and 'localport=8443' in c for c in cmds)
    assert any('add rule' in c and 'localport=11105' in c for c in cmds)
    assert not any('localport=5000' in c for c in cmds)


def test_api_config_save_reports_restart(tmp_path):
    cfg_path = str(tmp_path / 'config.yaml')
    config = _base_config(tmp_path)
    with open(cfg_path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    init_web_app(config, cfg_path, None, None, 1000)
    client = app.test_client()
    client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin-pass'})

    new_cfg = copy.deepcopy(config)
    new_cfg['pacs']['ip'] = '10.0.0.9'
    data = client.post('/api/config', json=new_cfg).get_json()
    assert data['success'] is True
    assert data['restart_required'] is True and data['changed_sections'] == ['pacs']
    assert data['restarting'] is False  # chạy từ mã nguồn: chỉ nhắc, không tự thoát tiến trình test
    assert 'khởi động lại' in data['message']

    same = client.post('/api/config', json=new_cfg).get_json()
    assert same['restart_required'] is False


def test_service_restart_scheduled_only_for_installed_build():
    import web_server
    with patch('threading.Timer') as timer:
        assert web_server._schedule_service_restart('test') is False
        timer.assert_not_called()
        with patch.object(web_server.sys, 'frozen', True, create=True):
            assert web_server._schedule_service_restart('test') is True
        timer.assert_called_once()


def test_invalid_ports_rejected(tmp_path):
    import pytest
    from utils import ConfigError, _validate_config
    cfg = _base_config(tmp_path)
    _validate_config(cfg)
    for web, sc in ((70000, 105), (5000, 5000), ('abc', 105)):
        bad = copy.deepcopy(cfg)
        bad['web_ui']['port'] = web
        bad['pacs']['storage_commitment']['listen_port'] = sc
        with pytest.raises(ConfigError):
            _validate_config(bad)

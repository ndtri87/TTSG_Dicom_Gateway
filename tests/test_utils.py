import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (  # noqa: E402
    ConfigError,
    ProcessedRegistry,
    compute_file_hash,
    dedupe_destination,
    delete_station,
    extract_metadata_from_filename,
    get_station_by_id,
    list_stations,
    load_config,
    merge_ris_metadata,
    upsert_station,
    wait_for_stable_file,
)

PATTERN_CONFIG = {
    'regex': r'^(?P<patient_id>[A-Za-z0-9]+)_(?P<patient_name>[^_]+)_(?P<study_date>\d{8})',
    'date_format': '%Y%m%d',
}


def test_extract_metadata_valid_filename():
    metadata, warnings = extract_metadata_from_filename(
        'BN001_NguyenVanA_20260811.png', PATTERN_CONFIG, 'UNKNOWN'
    )
    assert metadata['patient_id'] == 'BN001'
    assert metadata['patient_name'] == 'NguyenVanA'
    assert metadata['study_date'] == '20260811'
    assert warnings == []


def test_extract_metadata_invalid_filename_uses_defaults():
    metadata, warnings = extract_metadata_from_filename('random_scan.png', PATTERN_CONFIG, 'UNKNOWN')
    assert metadata['patient_id'] == 'UNKNOWN'
    assert metadata['patient_name'] == 'UNKNOWN'
    assert metadata['study_date'] == ''
    assert len(warnings) > 0


def test_extract_metadata_bad_date_falls_back_to_empty():
    metadata, warnings = extract_metadata_from_filename(
        'BN001_NguyenVanA_99999999.png', PATTERN_CONFIG, 'UNKNOWN'
    )
    assert metadata['study_date'] == ''
    assert any('StudyDate' in w for w in warnings)


def test_merge_ris_metadata_overrides_when_present():
    metadata = {'patient_id': 'BN001', 'patient_name': 'UNKNOWN', 'study_date': '20260811'}
    ris_data = {
        'patient_name': 'NGUYEN^VAN^A',
        'patient_birth_date': '19800101',
        'patient_sex': 'M',
        'accession_number': 'ACC000123',
    }
    merged = merge_ris_metadata(metadata, ris_data)
    assert merged['patient_name'] == 'NGUYEN VAN A'
    assert merged['patient_birth_date'] == '19800101'
    assert merged['patient_sex'] == 'M'
    assert merged['accession_number'] == 'ACC000123'
    assert merged['patient_id'] == 'BN001'


def test_merge_ris_metadata_keeps_original_when_none():
    metadata = {'patient_id': 'BN001', 'patient_name': 'UNKNOWN'}
    assert merge_ris_metadata(metadata, None) == metadata


def test_merge_ris_metadata_ignores_empty_fields():
    metadata = {'patient_id': 'BN001', 'patient_name': 'UNKNOWN'}
    ris_data = {'patient_name': '', 'patient_birth_date': '19800101'}
    merged = merge_ris_metadata(metadata, ris_data)
    assert merged['patient_name'] == 'UNKNOWN'
    assert merged['patient_birth_date'] == '19800101'


def test_wait_for_stable_file_detects_stable_file():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b'hello world')
        path = tmp.name
    try:
        assert wait_for_stable_file(path, interval_sec=0.1, required_stable_checks=2, timeout_sec=5) is True
    finally:
        os.remove(path)


def test_wait_for_stable_file_missing_file_returns_false():
    assert (
        wait_for_stable_file('/nonexistent/path/file.png', interval_sec=0.1, required_stable_checks=2, timeout_sec=1)
        is False
    )


def test_compute_file_hash_deterministic():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b'sample content')
        path = tmp.name
    try:
        h1 = compute_file_hash(path)
        h2 = compute_file_hash(path)
        assert h1 == h2
        assert len(h1) == 64
    finally:
        os.remove(path)


def test_dedupe_destination_avoids_collision():
    with tempfile.TemporaryDirectory() as tmp_dir:
        existing = os.path.join(tmp_dir, 'a.dcm')
        with open(existing, 'w') as f:
            f.write('x')
        result = dedupe_destination(existing)
        assert result == os.path.join(tmp_dir, 'a_1.dcm')


def test_processed_registry_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, 'registry.sqlite3')
        registry = ProcessedRegistry(db_path)
        try:
            assert registry.is_processed('abc123') is False
            registry.mark_processed('abc123', 'file.png', '1.2.3.4')
            assert registry.is_processed('abc123') is True
        finally:
            registry.close()


def test_load_config_missing_file_raises():
    try:
        load_config('/nonexistent/config.yaml')
        assert False, "Kỳ vọng ConfigError"
    except ConfigError:
        pass


def test_processed_registry_modality_stats():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, 'registry.sqlite3')
        registry = ProcessedRegistry(db_path)
        try:
            registry.record_study('us_file.png', {'patient_id': 'BN01', 'patient_name': 'Nguyen A', 'modality': 'US'}, 'SUCCESS')
            registry.record_study('es_file.png', {'patient_id': 'BN02', 'patient_name': 'Tran B', 'modality': 'ES'}, 'RETRYING')
            registry.record_study('cr_file.png', {'patient_id': 'BN03', 'patient_name': 'Le C', 'modality': 'CR'}, 'FAILED')

            stats = registry.get_modality_stats()
            assert 'US' in stats
            assert stats['US']['today']['success'] == 1
            assert stats['US']['last_patient']['patient_id'] == 'BN01'

            assert 'ES' in stats
            assert stats['ES']['today']['retrying'] == 1

            assert 'CR' in stats
            assert stats['CR']['today']['failed'] == 1
        finally:
            registry.close()


def test_processed_registry_get_completed_accessions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, 'registry.sqlite3')
        registry = ProcessedRegistry(db_path)
        try:
            # Ghi 1 ca SUCCESS có accession_number
            registry.record_study(
                'us_file.png',
                {'patient_id': 'BN01', 'patient_name': 'Nguyen A', 'accession_number': 'ACC1001', 'modality': 'US', 'study_date': '20260825'},
                'SUCCESS',
                sop_instance_uid='1.2.3.4.5.1'
            )
            # Ghi 1 ca FAILED có accession_number
            registry.record_study(
                'es_file.png',
                {'patient_id': 'BN02', 'patient_name': 'Tran B', 'accession_number': 'ACC1002', 'modality': 'ES', 'study_date': '20260825'},
                'FAILED',
                sop_instance_uid='1.2.3.4.5.2'
            )

            # Truy vấn danh sách completed accessions
            completed = registry.get_completed_accessions(['ACC1001', 'ACC1002', 'ACC1003'])
            assert 'ACC1001' in completed
            assert completed['ACC1001']['patient_id'] == 'BN01'
            assert completed['ACC1001']['sop_instance_uid'] == '1.2.3.4.5.1'
            assert 'ACC1002' not in completed  # Do trạng thái FAILED
            assert 'ACC1003' not in completed
        finally:
            registry.close()


def test_stations_crud():
    with tempfile.TemporaryDirectory() as tmp_dir:
        cfg_path = os.path.join(tmp_dir, 'config.yaml')
        config = {
            'pacs': {'ip': '127.0.0.1', 'port': 104, 'called_ae_title': 'PACS', 'calling_ae_title': 'GATEWAY'},
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
            'filename_pattern': {'regex': r'^(?P<patient_id>[A-Za-z0-9]+)', 'date_format': '%Y%m%d'},
            'metadata': {'default_value': 'UNKNOWN', 'specific_character_set': 'ISO_IR 192'},
            'retry': {'scan_interval_sec': 300, 'backoff_schedule_sec': [300, 600], 'max_attempts': 3},
            'logging': {'log_folder': tmp_dir, 'level': 'INFO', 'retention_days': 90},
            'stations': []
        }

        # 1. List default stations
        stations = list_stations(config)
        assert len(stations) >= 5
        assert any(s['id'] == 'US_01' for s in stations)
        assert any(s['id'] == 'ES_01' for s in stations)

        # 2. Get station by id
        us_st = get_station_by_id(config, 'us_01')
        assert us_st is not None
        assert 'US' in us_st['allowed_modalities']

        # 3. Add new station
        new_st_data = {
            'id': 'CT_01',
            'name': 'Phòng Chụp Cắt Lớp Vi Tính 01',
            'department': 'Khoa Chẩn đoán hình ảnh',
            'icon': '🌀',
            'allowed_modalities': ['CT'],
            'default_modality': 'CT'
        }
        added = upsert_station(config, cfg_path, new_st_data)
        assert added['id'] == 'CT_01'
        assert get_station_by_id(config, 'CT_01') is not None

        # 4. Update station
        update_data = {
            'id': 'CT_01',
            'name': 'Phòng Chụp CT 128 Dãy',
            'allowed_modalities': ['CT', 'DOC'],
            'default_modality': 'CT'
        }
        updated = upsert_station(config, cfg_path, update_data)
        assert updated['name'] == 'Phòng Chụp CT 128 Dãy'
        assert 'DOC' in updated['allowed_modalities']

        # 5. Delete station
        ok = delete_station(config, cfg_path, 'CT_01')
        assert ok is True
        assert get_station_by_id(config, 'CT_01') is None




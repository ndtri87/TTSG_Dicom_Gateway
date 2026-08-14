import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (  # noqa: E402
    ConfigError,
    ProcessedRegistry,
    compute_file_hash,
    dedupe_destination,
    extract_metadata_from_filename,
    load_config,
    merge_ris_metadata,
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

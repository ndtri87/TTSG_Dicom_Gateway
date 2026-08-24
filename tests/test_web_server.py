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
            assert es_mod['status'] == 'WARNING'
            assert es_mod['stats_today']['retrying'] == 1
        finally:
            registry.close()



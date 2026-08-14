import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pydicom  # noqa: E402
from PIL import Image  # noqa: E402

from dicom_builder import DicomBuildError, build_dicom_from_file  # noqa: E402

METADATA_TEMPLATE = {
    'patient_id': 'BN001',
    'patient_name': 'NguyenVanA',
    'study_date': '20260811',
    'accession_number': 'UNKNOWN',
    'default_value': 'UNKNOWN',
}


def _make_config(tmp_dir):
    return {
        'paths': {'dicom_staging_folder': tmp_dir},
        'metadata': {
            'default_value': 'UNKNOWN',
            'specific_character_set': 'ISO_IR 192',
            'institution_name': 'Test Clinic',
            'modality': 'OT',
        },
    }


def test_build_secondary_capture_from_png():
    with tempfile.TemporaryDirectory() as tmp_dir:
        img_path = os.path.join(tmp_dir, 'BN001_NguyenVanA_20260811.png')
        Image.new('RGB', (10, 10), color='white').save(img_path)

        config = _make_config(tmp_dir)
        output_path, sop_uid = build_dicom_from_file(img_path, METADATA_TEMPLATE, config)

        assert os.path.exists(output_path)
        ds = pydicom.dcmread(output_path)
        assert ds.PatientID == 'BN001'
        assert str(ds.PatientName) == 'NguyenVanA'
        assert ds.StudyDate == '20260811'
        assert ds.SOPInstanceUID == sop_uid
        assert ds.Rows == 10
        assert ds.Columns == 10
        assert ds.SpecificCharacterSet == 'ISO_IR 192'
        assert ds.PhotometricInterpretation == 'RGB'


def test_build_secondary_capture_grayscale():
    with tempfile.TemporaryDirectory() as tmp_dir:
        img_path = os.path.join(tmp_dir, 'BN003_LeVanC_20260811.jpg')
        Image.new('L', (8, 6), color=128).save(img_path)

        config = _make_config(tmp_dir)
        metadata = dict(METADATA_TEMPLATE)
        metadata['patient_id'] = 'BN003'
        output_path, _ = build_dicom_from_file(img_path, metadata, config)

        ds = pydicom.dcmread(output_path)
        assert ds.PhotometricInterpretation == 'MONOCHROME2'
        assert ds.SamplesPerPixel == 1


def test_build_encapsulated_pdf():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, 'BN002_TranThiB_20260811.pdf')
        with open(pdf_path, 'wb') as f:
            f.write(b'%PDF-1.4\n%mock pdf content\n%%EOF')

        config = _make_config(tmp_dir)
        metadata = dict(METADATA_TEMPLATE)
        metadata['patient_id'] = 'BN002'
        output_path, sop_uid = build_dicom_from_file(pdf_path, metadata, config)

        assert os.path.exists(output_path)
        ds = pydicom.dcmread(output_path)
        assert ds.PatientID == 'BN002'
        assert ds.MIMETypeOfEncapsulatedDocument == 'application/pdf'
        assert ds.SOPInstanceUID == sop_uid


def test_build_dicom_unsupported_extension_raises():
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_path = os.path.join(tmp_dir, 'file.txt')
        with open(bad_path, 'w') as f:
            f.write('not an image')
        config = _make_config(tmp_dir)
        try:
            build_dicom_from_file(bad_path, METADATA_TEMPLATE, config)
            assert False, "Kỳ vọng DicomBuildError"
        except DicomBuildError:
            pass


def test_build_secondary_capture_corrupt_image_raises():
    with tempfile.TemporaryDirectory() as tmp_dir:
        bad_img_path = os.path.join(tmp_dir, 'corrupt.png')
        with open(bad_img_path, 'wb') as f:
            f.write(b'not a real png')
        config = _make_config(tmp_dir)
        try:
            build_dicom_from_file(bad_img_path, METADATA_TEMPLATE, config)
            assert False, "Kỳ vọng DicomBuildError"
        except DicomBuildError:
            pass


def test_build_dicom_with_report_metadata():
    with tempfile.TemporaryDirectory() as tmp_dir:
        pdf_path = os.path.join(tmp_dir, 'Report_BN005.pdf')
        with open(pdf_path, 'wb') as f:
            f.write(b'%PDF-1.4\n%mock report pdf\n%%EOF')

        config = _make_config(tmp_dir)
        metadata = dict(METADATA_TEMPLATE)
        metadata.update({
            'patient_id': 'BN005',
            'instance_number': 1,
            'document_title': 'PHIẾU KẾT QUẢ CẬN LÂM SÀNG',
            'series_description': 'Diagnostic Report',
        })
        output_path, _ = build_dicom_from_file(pdf_path, metadata, config)

        ds = pydicom.dcmread(output_path)
        assert ds.InstanceNumber == '1'
        assert ds.SeriesDescription == 'Diagnostic Report'
        assert ds.DocumentTitle == 'PHIẾU KẾT QUẢ CẬN LÂM SÀNG'


"""Công cụ kiểm tra trực tiếp file DICOM đã sinh ra và gửi thử C-ECHO / C-STORE tới PACS Server."""
import os
import sys
import pydicom
from pydicom.uid import generate_uid

sys.stdout.reconfigure(encoding='utf-8')

from dicom_builder import build_dicom_from_file
from dicom_sender import DicomSender
from utils import load_config

def main():
    print("=" * 60)
    print("      DICOM GATEWAY - PACSTTSG DIAGNOSTIC TOOL")
    print("=" * 60)

    config = load_config('config.yaml')
    pacs_cfg = config['pacs']
    print(f"[1] PACS Server: {pacs_cfg['ip']}:{pacs_cfg['port']} (Called AE: {pacs_cfg['called_ae_title']}, Calling AE: {pacs_cfg['calling_ae_title']})")

    sender = DicomSender(pacs_cfg, None)
    ok, err = sender.test_connection()
    if ok:
        print("[OK] [C-ECHO PACS] Ket noi C-ECHO toi PACS thanh cong 100%!")
    else:
        print(f"[FAIL] [C-ECHO PACS] That bai: {err}")

    # Build test file
    sample_metadata = {
        'patient_id': '18000991',
        'patient_name': 'ADMIN TEST1',
        'accession_number': '3040784',
        'study_date': '20260814',
        'study_time': '153000',
        'modality': 'US',
        'study_description': 'Sieu am o bung tong quat',
        'instance_number': 1,
    }

    # Search for any image/pdf file in data/inbox or create temporary dummy image
    test_img = './data/test_sample.png'
    if not os.path.exists(test_img):
        from PIL import Image
        Image.new('RGB', (100, 100), color='white').save(test_img)

    dicom_path, sop_uid = build_dicom_from_file(test_img, sample_metadata, config)
    print(f"\n[2] Đã đóng gói thử file DICOM: {dicom_path}")

    ds = pydicom.dcmread(dicom_path)
    print("\n--- THÔNG SỐ DICOM HEADER SẼ GỬI SANG PACS ---")
    print(f"  - PatientID          : {ds.PatientID}")
    print(f"  - PatientName        : {ds.PatientName}")
    print(f"  - AccessionNumber    : {ds.AccessionNumber}")
    print(f"  - StudyDate / Time   : {ds.StudyDate} / {ds.StudyTime}")
    print(f"  - Modality           : {ds.Modality}")
    print(f"  - SOPClassUID        : {ds.SOPClassUID} ({ds.SOPClassUID.name})")
    print(f"  - SOPInstanceUID     : {ds.SOPInstanceUID}")
    print(f"  - StudyInstanceUID   : {ds.StudyInstanceUID}")
    print(f"  - SeriesInstanceUID  : {ds.SeriesInstanceUID}")
    print(f"  - ImageType          : {getattr(ds, 'ImageType', 'N/A')}")
    print(f"  - CharacterSet       : {getattr(ds, 'SpecificCharacterSet', 'Default')}")
    print(f"  - TransferSyntaxUID  : {ds.file_meta.TransferSyntaxUID} ({ds.file_meta.TransferSyntaxUID.name})")
    print("----------------------------------------------")

    print("\n[3] Gui thu C-STORE sang PACS Server...")
    sent_ok, send_err = sender.send(dicom_path)
    if sent_ok:
        print("[OK] [C-STORE PACS] Gui C-STORE thanh cong 100%! Status code: 0x0000 (Success)")
    else:
        print(f"[FAIL] [C-STORE PACS] Loi gui C-STORE: {send_err}")

if __name__ == '__main__':
    main()

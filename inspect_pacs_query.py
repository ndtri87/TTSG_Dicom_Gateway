"""Công cụ chẩn đoán: hỏi TRỰC TIẾP PACS Server (qua DICOM C-FIND Query/Retrieve,
KHÔNG qua web viewer) xem một Study/AccessionNumber có thực sự được lưu trong
database của PACS hay không.

Dùng để tách bạch 2 khả năng khi Gateway báo C-STORE thành công (status 0x0000)
nhưng web viewer (VD iDiVi/BKPACS) không hiển thị:
  - PACS THỰC SỰ có lưu (script này tìm thấy) -> lỗi nằm ở web viewer/index,
    không phải ở Gateway hay PACS storage engine.
  - PACS KHÔNG có lưu (script này không tìm thấy gì) -> PACS đã âm thầm từ chối/
    không lưu đối tượng dù trả C-STORE status thành công -> cần báo PACS vendor.

Cách chạy:
    python inspect_pacs_query.py --accession-number 3042438
    python inspect_pacs_query.py --patient-id 18000991
"""
import argparse
import sys

sys.stdout.reconfigure(encoding='utf-8')

from pydicom.dataset import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind

from utils import load_config


def build_query(patient_id, accession_number, patient_name, study_date):
    query = Dataset()
    query.QueryRetrieveLevel = 'STUDY'
    query.PatientID = patient_id or ''
    query.PatientName = f"*{patient_name}*" if patient_name else ''
    query.AccessionNumber = accession_number or ''
    query.StudyDate = study_date or ''
    query.StudyInstanceUID = ''
    query.StudyDescription = ''
    query.ModalitiesInStudy = ''
    query.NumberOfStudyRelatedInstances = ''
    return query


def main():
    parser = argparse.ArgumentParser(
        description="Hỏi trực tiếp PACS (C-FIND Query/Retrieve) xem Study có tồn tại thật không, "
                    "độc lập với web viewer."
    )
    parser.add_argument('--accession-number', default='', help="Tra theo AccessionNumber")
    parser.add_argument('--patient-id', default='', help="Tra theo PatientID")
    parser.add_argument('--patient-name', default='', help="Tra theo PatientName (khớp gần đúng)")
    parser.add_argument('--study-date', default='', help="Tra theo StudyDate (YYYYMMDD)")
    parser.add_argument('--config', default='config.yaml', help="Đường dẫn config.yaml")
    args = parser.parse_args()

    if not any([args.accession_number, args.patient_id, args.patient_name]):
        print("[!] Cần ít nhất 1 điều kiện lọc: --accession-number, --patient-id hoặc --patient-name")
        sys.exit(1)

    config = load_config(args.config)
    pacs_cfg = config['pacs']

    print("=" * 70)
    print("      PACS - TRUY VẤN TRỰC TIẾP (QUERY/RETRIEVE C-FIND)")
    print("      Bỏ qua web viewer, hỏi thẳng database của PACS Server")
    print("=" * 70)
    print(f"[*] PACS Server: {pacs_cfg['ip']}:{pacs_cfg['port']} "
          f"(Called AE: {pacs_cfg['called_ae_title']}, Calling AE: {pacs_cfg['calling_ae_title']})")
    print(f"[*] Bộ lọc: accession_number={args.accession_number!r} patient_id={args.patient_id!r} "
          f"patient_name={args.patient_name!r} study_date={args.study_date!r}")
    print("-" * 70)

    ae = AE(ae_title=pacs_cfg['calling_ae_title'])
    ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
    timeout = pacs_cfg.get('connect_timeout_sec', 10)
    ae.acse_timeout = timeout
    ae.network_timeout = timeout
    ae.dimse_timeout = timeout

    query = build_query(args.patient_id, args.accession_number, args.patient_name, args.study_date)

    assoc = ae.associate(pacs_cfg['ip'], int(pacs_cfg['port']), ae_title=pacs_cfg['called_ae_title'])
    if not assoc.is_established:
        print("[FAIL] Không thiết lập được association với PACS Server.")
        print("       -> PACS có thể không hỗ trợ Query/Retrieve trên cùng port với Storage,")
        print("          hoặc từ chối AE Title. Cần hỏi PACS admin về port/AE Query/Retrieve riêng.")
        sys.exit(1)

    count = 0
    try:
        responses = assoc.send_c_find(query, StudyRootQueryRetrieveInformationModelFind)
        for status, identifier in responses:
            if status is None:
                print("[FAIL] Không nhận được phản hồi (timeout/kết nối bị ngắt).")
                break
            if status.Status in (0xFF00, 0xFF01) and identifier is not None:
                count += 1
                print(f"\n########## TÌM THẤY #{count} (status=0x{status.Status:04X}) ##########")
                print(identifier)
            elif status.Status == 0x0000:
                pass
            else:
                print(f"[!] Status bất thường: 0x{status.Status:04X}")
    finally:
        assoc.release()

    print("-" * 70)
    if count == 0:
        print("[KẾT LUẬN] PACS KHÔNG có bản ghi nào khớp bộ lọc trên trong database của nó.")
        print("           => Dù C-STORE từng báo status 0x0000, PACS đã không thực sự lưu/index")
        print("              đối tượng này. Đây là lỗi phía PACS Server, không phải Gateway.")
        print("              Cần báo PACS vendor kèm SOPInstanceUID + thời điểm gửi để họ tra log.")
    else:
        print(f"[KẾT LUẬN] PACS THỰC SỰ CÓ {count} bản ghi khớp trong database.")
        print("           => Dữ liệu đã lưu đúng phía PACS. Vấn đề nằm ở web viewer")
        print("              (iDiVi/BKPACS) chưa hiển thị/đánh index, không phải do Gateway hay")
        print("              PACS storage engine.")


if __name__ == '__main__':
    main()

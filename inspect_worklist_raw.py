"""Công cụ chẩn đoán: dump TOÀN BỘ dữ liệu thô mà RIS Worklist Server trả về
qua C-FIND (Modality Worklist), không giới hạn ở các tag mà worklist_client.py
hiện đang đọc. Dùng để tìm field nào thực sự chứa AccessionNumber/số chỉ định
đúng khi (0008,0050) AccessionNumber mà RIS trả về không khớp với đơn gốc từ HIS
(ví dụ số đúng nằm ở FillerOrderNumberImagingServiceRequest thay vì AccessionNumber).

Cách chạy:
    python inspect_worklist_raw.py                  # liệt kê toàn bộ Worklist hôm nay
    python inspect_worklist_raw.py --patient-id 18000991
    python inspect_worklist_raw.py --date 20260731
"""
import argparse
import sys

sys.stdout.reconfigure(encoding='utf-8')

from pydicom.dataset import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind

from utils import load_config


def build_query(patient_id, patient_name, date_str, modality):
    query = Dataset()
    # Các tag chuẩn mà worklist_client.py hiện đã đọc
    query.PatientID = patient_id or ''
    query.PatientName = f"*{patient_name}*" if patient_name else ''
    query.PatientBirthDate = ''
    query.PatientSex = ''
    query.AccessionNumber = ''
    query.StudyInstanceUID = ''
    query.StudyDescription = ''
    query.ReferringPhysicianName = ''

    # Các tag DICOM MWL chuẩn dùng để mang số chỉ định/order từ HL7 (OBR-2/OBR-3),
    # nhưng hiện KHÔNG được worklist_client.py yêu cầu/đọc — rất có thể số
    # AccessionNumber đúng (3022292 trong ca thực tế) nằm ở đây.
    query.RequestedProcedureID = ''
    query.RequestedProcedureDescription = ''
    query.RequestedProcedureCodeSequence = []
    query.PlacerOrderNumberImagingServiceRequest = ''
    query.FillerOrderNumberImagingServiceRequest = ''
    query.RequestingPhysician = ''
    query.AdmissionID = ''
    query.OtherPatientIDsSequence = []

    sps = Dataset()
    sps.Modality = modality or ''
    sps.ScheduledStationAETitle = ''
    sps.ScheduledProcedureStepStartDate = date_str or ''
    sps.ScheduledProcedureStepStartTime = ''
    sps.ScheduledProcedureStepDescription = ''
    sps.ScheduledProcedureStepID = ''
    sps.ScheduledPerformingPhysicianName = ''
    query.ScheduledProcedureStepSequence = [sps]

    return query


def main():
    parser = argparse.ArgumentParser(description="Dump thô dữ liệu C-FIND Worklist từ RIS Server")
    parser.add_argument('--patient-id', default='', help="Lọc theo PatientID (để trống = tất cả)")
    parser.add_argument('--patient-name', default='', help="Lọc theo PatientName (khớp gần đúng)")
    parser.add_argument('--date', default='', help="Lọc theo ScheduledProcedureStepStartDate (YYYYMMDD)")
    parser.add_argument('--modality', default='', help="Lọc theo Modality (VD: ECG, US, CR...)")
    parser.add_argument('--config', default='config.yaml', help="Đường dẫn config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    ris_cfg = config['ris']

    print("=" * 70)
    print("      RIS WORKLIST - RAW C-FIND DIAGNOSTIC TOOL")
    print("=" * 70)
    print(f"[*] RIS Server: {ris_cfg['ip']}:{ris_cfg['port']} "
          f"(Called AE: {ris_cfg['called_ae_title']}, Calling AE: {ris_cfg['calling_ae_title']})")
    print(f"[*] Bộ lọc: patient_id={args.patient_id!r} patient_name={args.patient_name!r} "
          f"date={args.date!r} modality={args.modality!r}")
    print("-" * 70)

    ae = AE(ae_title=ris_cfg['calling_ae_title'])
    ae.add_requested_context(ModalityWorklistInformationFind)
    timeout = ris_cfg.get('connect_timeout_sec', 10)
    ae.acse_timeout = timeout
    ae.network_timeout = timeout
    ae.dimse_timeout = timeout

    query = build_query(args.patient_id, args.patient_name, args.date, args.modality)

    assoc = ae.associate(ris_cfg['ip'], int(ris_cfg['port']), ae_title=ris_cfg['called_ae_title'])
    if not assoc.is_established:
        print("[FAIL] Không thiết lập được association với RIS Server.")
        sys.exit(1)

    count = 0
    try:
        responses = assoc.send_c_find(query, ModalityWorklistInformationFind)
        for status, identifier in responses:
            if status is None:
                print("[FAIL] Không nhận được phản hồi (timeout/kết nối bị ngắt).")
                break
            if status.Status in (0xFF00, 0xFF01) and identifier is not None:
                count += 1
                print(f"\n########## KẾT QUẢ #{count} (status=0x{status.Status:04X}) ##########")
                print(identifier)
            elif status.Status == 0x0000:
                pass  # Final success status, không có identifier kèm theo
            else:
                print(f"[!] Status bất thường: 0x{status.Status:04X}")
    finally:
        assoc.release()

    print("-" * 70)
    if count == 0:
        print("[!] RIS không trả về kết quả nào khớp bộ lọc trên.")
    else:
        print(f"[OK] Tổng cộng {count} bản ghi. Hãy tìm giá trị AccessionNumber đúng "
              f"(theo HIS) trong các tag ở trên, đặc biệt:\n"
              f"     - FillerOrderNumberImagingServiceRequest (0040,2017)\n"
              f"     - PlacerOrderNumberImagingServiceRequest (0040,2016)\n"
              f"     - RequestedProcedureID (0040,1001)\n"
              f"     - AccessionNumber (0008,0050)")


if __name__ == '__main__':
    main()

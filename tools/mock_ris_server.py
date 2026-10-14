"""RIS/Modality Worklist giả lập để test truy vấn C-FIND cục bộ trước khi
kết nối RIS thật. Trả về 1 bản ghi bệnh nhân cố định cho MỌI PatientID được
hỏi, chỉ nhằm mục đích kiểm thử luồng worklist_client.py."""
import argparse

from pydicom.dataset import Dataset
from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityWorklistInformationFind


def handle_find(event, patient_name, birth_date, sex, accession_number):
    query = event.identifier
    patient_id = query.get('PatientID', '')
    if not patient_id or patient_id == '?':
        patient_id = 'BN18000991'
    print(f"[MOCK RIS] Nhận C-FIND cho PatientID={patient_id}")

    identifier = Dataset()
    identifier.PatientID = patient_id
    identifier.PatientName = patient_name
    identifier.PatientBirthDate = birth_date
    identifier.PatientSex = sex
    identifier.AccessionNumber = accession_number
    identifier.StudyInstanceUID = '1.2.840.113619.2.55.3.2831158860.678'

    sps = Dataset()
    sps.Modality = 'US'
    sps.ScheduledProcedureStepDescription = 'Sieu am o bung tong quat'
    sps.ScheduledStationAETitle = 'WORKLIST'
    identifier.ScheduledProcedureStepSequence = [sps]

    yield (0xFF00, identifier)
    yield (0x0000, None)


def main():
    parser = argparse.ArgumentParser(description="Mock RIS/Worklist server để test C-FIND cục bộ")
    parser.add_argument('--port', type=int, default=6002)
    parser.add_argument('--ae-title', default='RISTTSG')
    parser.add_argument('--patient-name', default='NGUYEN^VAN^A')
    parser.add_argument('--birth-date', default='19800101')
    parser.add_argument('--sex', default='M')
    parser.add_argument('--accession-number', default='ACC000123')
    args = parser.parse_args()

    handlers = [
        (
            evt.EVT_C_FIND,
            lambda event: handle_find(
                event, args.patient_name, args.birth_date, args.sex, args.accession_number
            ),
        ),
    ]

    ae = AE(ae_title=args.ae_title)
    ae.add_supported_context(ModalityWorklistInformationFind)

    print(f"[MOCK RIS] Đang lắng nghe trên port {args.port} với AE Title '{args.ae_title}'...")
    print(f"[MOCK RIS] Mọi truy vấn sẽ trả về: {args.patient_name}, sinh {args.birth_date}, giới tính {args.sex}")
    ae.start_server(('0.0.0.0', args.port), evt_handlers=handlers)


if __name__ == '__main__':
    main()

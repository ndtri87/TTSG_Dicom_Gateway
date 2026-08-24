"""Tra cứu thông tin hành chính bệnh nhân (PatientName, PatientBirthDate,
PatientSex, AccessionNumber) từ RIS qua DICOM Modality Worklist (C-FIND),
theo PatientID trích được từ tên file. Nếu RIS không phản hồi hoặc không có
dữ liệu, trả về None — pipeline chính sẽ dùng giá trị mặc định, không dừng
service (xem PRD mục 5: không được văng lỗi vì thiếu metadata)."""
from pydicom.dataset import Dataset
from pynetdicom import AE
from pynetdicom.sop_class import ModalityWorklistInformationFind


class WorklistClient:
    def __init__(self, ris_config, logger):
        self.ip = ris_config['ip']
        self.port = ris_config['port']
        self.called_ae_title = ris_config['called_ae_title']
        self.calling_ae_title = ris_config['calling_ae_title']
        self.timeout = ris_config.get('connect_timeout_sec', 10)
        self.logger = logger

    def lookup_patient(self, patient_id):
        """Trả về dict {patient_name, patient_birth_date, patient_sex,
        accession_number} cho bản ghi Worklist đầu tiên khớp PatientID,
        hoặc None nếu không tìm thấy / lỗi kết nối."""
        ae = AE(ae_title=self.calling_ae_title)
        ae.add_requested_context(ModalityWorklistInformationFind)
        ae.acse_timeout = self.timeout
        ae.network_timeout = self.timeout
        ae.dimse_timeout = self.timeout

        query = Dataset()
        query.PatientID = patient_id
        query.PatientName = ''
        query.PatientBirthDate = ''
        query.PatientSex = ''
        query.AccessionNumber = ''
        query.StudyInstanceUID = ''
        query.StudyDescription = ''
        sps = Dataset()
        sps.Modality = ''
        sps.ScheduledStationAETitle = ''
        query.ScheduledProcedureStepSequence = [sps]

        try:
            assoc = ae.associate(self.ip, self.port, ae_title=self.called_ae_title)
        except Exception as exc:
            self.logger.warning(f"Không kết nối được RIS để tra cứu PatientID {patient_id}: {exc}")
            return None

        if not assoc.is_established:
            self.logger.warning(f"Không thiết lập được association với RIS cho PatientID {patient_id}")
            return None

        result = None
        try:
            responses = assoc.send_c_find(query, ModalityWorklistInformationFind)
            for status, identifier in responses:
                if status is None:
                    break
                if status.Status in (0xFF00, 0xFF01) and identifier is not None:
                    raw_name = str(identifier.PatientName) if 'PatientName' in identifier else ''
                    clean_name = ' '.join(raw_name.replace('^', ' ').split())
                    result = {
                        'patient_name': clean_name,
                        'patient_birth_date': str(getattr(identifier, 'PatientBirthDate', '')),
                        'patient_sex': str(getattr(identifier, 'PatientSex', '')),
                        'accession_number': str(getattr(identifier, 'AccessionNumber', '')),
                        'study_instance_uid': str(getattr(identifier, 'StudyInstanceUID', '')),
                        'study_description': str(getattr(identifier, 'StudyDescription', '')),
                    }
                    break
        except Exception as exc:
            self.logger.warning(f"Lỗi khi truy vấn RIS cho PatientID {patient_id}: {exc}")
        finally:
            assoc.release()

        if result is None:
            self.logger.warning(f"Không tìm thấy dữ liệu RIS cho PatientID {patient_id}, dùng giá trị từ tên file")
        return result

    def query_worklist(self, date_str=None, patient_id=None, patient_name=None, modality=None):
        """Truy vấn danh sách ca chỉ định từ RIS Worklist theo ngày, mã BN, tên BN hoặc modality."""
        ae = AE(ae_title=self.calling_ae_title)
        ae.add_requested_context(ModalityWorklistInformationFind)
        ae.acse_timeout = self.timeout
        ae.network_timeout = self.timeout
        ae.dimse_timeout = self.timeout

        query = Dataset()
        query.PatientID = patient_id if patient_id else ''
        query.PatientName = f"*{patient_name}*" if patient_name else ''
        query.PatientBirthDate = ''
        query.PatientSex = ''
        query.AccessionNumber = ''
        query.StudyInstanceUID = ''
        query.StudyDescription = ''

        sps = Dataset()
        sps.Modality = modality if modality else ''
        sps.ScheduledProcedureStepStartDate = date_str if date_str else ''
        sps.ScheduledProcedureStepDescription = ''
        sps.ScheduledStationAETitle = ''
        query.ScheduledProcedureStepSequence = [sps]

        try:
            assoc = ae.associate(self.ip, self.port, ae_title=self.called_ae_title)
        except Exception as exc:
            if self.logger:
                self.logger.warning(f"Không kết nối được RIS Worklist: {exc}")
            return []

        if not assoc.is_established:
            if self.logger:
                self.logger.warning("Không thiết lập được association với RIS Worklist")
            return []

        results = []
        try:
            responses = assoc.send_c_find(query, ModalityWorklistInformationFind)
            for status, identifier in responses:
                if status is None:
                    break
                if status.Status in (0xFF00, 0xFF01) and identifier is not None:
                    study_desc = getattr(identifier, 'StudyDescription', '') or ''
                    mod = ''
                    scheduled_date = ''
                    scheduled_time = ''
                    if 'ScheduledProcedureStepSequence' in identifier and len(identifier.ScheduledProcedureStepSequence) > 0:
                        step = identifier.ScheduledProcedureStepSequence[0]
                        if not study_desc:
                            study_desc = getattr(step, 'ScheduledProcedureStepDescription', '') or getattr(step, 'ScheduledProcedureDescription', '')
                        mod = getattr(step, 'Modality', '')
                        scheduled_date = getattr(step, 'ScheduledProcedureStepStartDate', '') or ''
                        scheduled_time = getattr(step, 'ScheduledProcedureStepStartTime', '') or ''

                    raw_pname = str(getattr(identifier, 'PatientName', ''))
                    clean_pname = ' '.join(raw_pname.replace('^', ' ').split())

                    results.append({
                        'patient_id': str(getattr(identifier, 'PatientID', '')),
                        'patient_name': clean_pname,
                        'patient_birth_date': str(getattr(identifier, 'PatientBirthDate', '')),
                        'patient_sex': str(getattr(identifier, 'PatientSex', '')),
                        'accession_number': str(getattr(identifier, 'AccessionNumber', '')),
                        'study_instance_uid': str(getattr(identifier, 'StudyInstanceUID', '')),
                        'study_description': str(study_desc),
                        'modality': str(mod),
                        # Ngày giờ chỉ định thực tế (0040,0002 & 0040,0003)
                        'scheduled_date': str(scheduled_date),
                        'scheduled_time': str(scheduled_time),
                    })
        except Exception as exc:
            if self.logger:
                self.logger.warning(f"Lỗi truy vấn RIS Worklist: {exc}")
        finally:
            assoc.release()

        # Mặc định ca mới nhất nằm ở đầu danh sách
        results.sort(key=lambda x: (x.get('scheduled_date', ''), x.get('scheduled_time', ''), x.get('accession_number', '')), reverse=True)

        return results

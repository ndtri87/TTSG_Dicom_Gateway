"""DICOM C-STORE client: kết nối tới PACS Server và đẩy file DICOM lên."""
import pydicom
from pynetdicom import AE

from dicom_builder import ENCAPSULATED_PDF_SOP_CLASS, SECONDARY_CAPTURE_SOP_CLASS
from pynetdicom.sop_class import Verification


class DicomSender:
    def __init__(self, pacs_config, logger):
        self.ip = pacs_config['ip']
        self.port = pacs_config['port']
        self.called_ae_title = pacs_config['called_ae_title']
        self.calling_ae_title = pacs_config['calling_ae_title']
        self.timeout = pacs_config.get('connect_timeout_sec', 10)
        self.logger = logger

        from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
        from pynetdicom.sop_class import (
            SecondaryCaptureImageStorage,
            UltrasoundImageStorage,
            UltrasoundMultiFrameImageStorage,
            ComputedRadiographyImageStorage,
            DigitalXRayImageStorageForPresentation,
            EncapsulatedPDFStorage,
            VLEndoscopicImageStorage,
            VLPhotographicImageStorage,
        )
        transfer_syntaxes = [ExplicitVRLittleEndian, ImplicitVRLittleEndian]

        self.ae = AE(ae_title=self.calling_ae_title)
        sop_classes = [
            SecondaryCaptureImageStorage,
            UltrasoundImageStorage,
            UltrasoundMultiFrameImageStorage,
            ComputedRadiographyImageStorage,
            DigitalXRayImageStorageForPresentation,
            EncapsulatedPDFStorage,
            VLEndoscopicImageStorage,
            VLPhotographicImageStorage,
        ]
        for sop in sop_classes:
            self.ae.add_requested_context(sop, transfer_syntaxes)
        self.ae.network_timeout = self.timeout
        self.ae.acse_timeout = self.timeout
        self.ae.dimse_timeout = self.timeout

    def test_connection(self):
        """Thực hiện C-ECHO tới PACS Server để kiểm tra kết nối."""
        ae = AE(ae_title=self.calling_ae_title)
        ae.add_requested_context(Verification)
        ae.acse_timeout = self.timeout
        ae.network_timeout = self.timeout
        ae.dimse_timeout = self.timeout
        try:
            assoc = ae.associate(self.ip, self.port, ae_title=self.called_ae_title)
            if not assoc.is_established:
                return False, "Không thiết lập được association với PACS Server"
            status = assoc.send_c_echo()
            assoc.release()
            if status and status.Status == 0x0000:
                return True, None
            return False, f"PACS từ chối C-ECHO với status: 0x{status.Status:04X}"
        except Exception as exc:
            return False, f"Lỗi kết nối C-ECHO PACS: {exc}"

    def send(self, dataset_path):
        """Gửi một file .dcm lên PACS. Trả về (success: bool, error: str|None)."""
        try:
            ds = pydicom.dcmread(dataset_path)
        except Exception as exc:
            return False, f"Không đọc được file DICOM: {exc}"

        try:
            assoc = self.ae.associate(self.ip, self.port, ae_title=self.called_ae_title)
        except Exception as exc:
            return False, f"Không thể kết nối PACS ({self.ip}:{self.port}): {exc}"

        if not assoc.is_established:
            return False, f"Không thiết lập được association với PACS Server ({self.ip}:{self.port}, AE: {self.called_ae_title})"

        try:
            status = assoc.send_c_store(ds)
        except Exception as exc:
            assoc.abort()
            return False, f"Lỗi khi gửi C-STORE: {exc}"
        finally:
            if assoc.is_alive():
                assoc.release()

        if status is None:
            return False, "Không nhận được phản hồi C-STORE từ PACS"

        if status.Status == 0x0000:
            return True, None

        return False, f"PACS trả về status lỗi: 0x{status.Status:04X}"

    def close(self):
        pass

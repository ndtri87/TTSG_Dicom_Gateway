"""Chuyển đổi ảnh (.png/.jpg) và tài liệu (.pdf) sang chuẩn DICOM,
gán metadata bắt buộc và sinh UID định danh duy nhất."""
import os

from PIL import Image
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

SECONDARY_CAPTURE_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.7'
ULTRASOUND_IMAGE_STORAGE_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.6.1'
CR_IMAGE_STORAGE_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.1'
DIGITAL_XRAY_IMAGE_STORAGE_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.1.1'
ENCAPSULATED_PDF_SOP_CLASS = '1.2.840.10008.5.1.4.1.1.104.1'


class DicomBuildError(Exception):
    pass


IMPLEMENTATION_CLASS_UID = '1.2.826.0.1.3680043.8.498.1.0'
IMPLEMENTATION_VERSION_NAME = 'GATEWAY_1.0'


def _new_file_meta(sop_class_uid, sop_instance_uid):
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = sop_class_uid
    file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = IMPLEMENTATION_CLASS_UID
    file_meta.ImplementationVersionName = IMPLEMENTATION_VERSION_NAME
    return file_meta


def _apply_common_metadata(ds, metadata, sop_class_uid, sop_instance_uid, study_uid, series_uid):
    import re
    from datetime import datetime

    ds.SpecificCharacterSet = metadata.get('specific_character_set', 'ISO_IR 192')
    ds.SOPClassUID = sop_class_uid
    ds.SOPInstanceUID = sop_instance_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid

    raw_name = metadata.get('patient_name', '')
    clean_name = ' '.join(str(raw_name).replace('^', ' ').split())
    ds.PatientName = clean_name
    ds.PatientID = str(metadata['patient_id']).strip()

    # Chuẩn hóa PatientBirthDate (VR DA: YYYYMMDD 8 chữ số)
    clean_dob = re.sub(r'\D', '', str(metadata.get('patient_birth_date', '')))
    ds.PatientBirthDate = clean_dob if len(clean_dob) == 8 else ''

    # Chuẩn hóa PatientSex (VR CS: M/F/O)
    raw_sex = str(metadata.get('patient_sex', '')).strip().upper()
    if raw_sex in ('M', 'MALE', 'NAM', '1'):
        ds.PatientSex = 'M'
    elif raw_sex in ('F', 'FEMALE', 'NỮ', 'NU', '2'):
        ds.PatientSex = 'F'
    elif raw_sex in ('O', 'OTHER', 'KHÁC', 'KHAC'):
        ds.PatientSex = 'O'
    else:
        ds.PatientSex = ''

    # Chuẩn hóa StudyDate & StudyTime (VR DA & TM)
    raw_study_date = re.sub(r'\D', '', str(metadata.get('study_date', '')))
    study_date = raw_study_date if len(raw_study_date) == 8 else datetime.now().strftime('%Y%m%d')

    raw_study_time = re.sub(r'\D', '', str(metadata.get('study_time', '')))
    study_time = raw_study_time[:6] if len(raw_study_time) >= 6 else datetime.now().strftime('%H%M%S')

    ds.StudyDate = study_date
    ds.StudyTime = study_time
    ds.SeriesDate = study_date
    ds.SeriesTime = study_time
    ds.AcquisitionDate = study_date
    ds.AcquisitionTime = study_time
    ds.ContentDate = study_date
    ds.ContentTime = study_time
    ds.InstanceCreationDate = study_date
    ds.InstanceCreationTime = study_time

    ds.StudyID = str(metadata.get('study_id') or metadata.get('accession_number') or metadata['patient_id']).strip()
    ds.AccessionNumber = str(metadata.get('accession_number', metadata['default_value'])).strip()
    ds.SeriesNumber = str(metadata.get('series_number', '1'))
    ds.InstanceNumber = str(metadata.get('instance_number', '1'))

    ds.ReferringPhysicianName = metadata.get('referring_physician', '')
    ds.Manufacturer = 'DICOM Gateway'
    if metadata.get('institution_name'):
        ds.InstitutionName = metadata['institution_name']
    if metadata.get('study_description'):
        ds.StudyDescription = metadata['study_description']
    if metadata.get('series_description'):
        ds.SeriesDescription = metadata['series_description']
    if metadata.get('document_title'):
        ds.DocumentTitle = metadata['document_title']


def generate_deterministic_uid(entropy_str, prefix='1.2.826.0.1.3680043.8.498.'):
    import hashlib
    clean_entropy = str(entropy_str).strip()
    if not clean_entropy or clean_entropy == 'UNKNOWN':
        return generate_uid()
    hex_hash = hashlib.sha256(clean_entropy.encode('utf-8')).hexdigest()
    numeric_suffix = str(int(hex_hash[:16], 16))
    full_uid = f"{prefix}{numeric_suffix}"
    return full_uid[:64]


def build_secondary_capture_image(image_path, metadata, output_path):
    try:
        img = Image.open(image_path)
        img.load()
    except Exception as exc:
        raise DicomBuildError(f"Không đọc được ảnh: {exc}") from exc

    if img.mode not in ('L', 'RGB'):
        img = img.convert('RGB')

    modality = str(metadata.get('modality', 'OT')).strip().upper()
    if modality == 'US':
        sop_class_uid = ULTRASOUND_IMAGE_STORAGE_SOP_CLASS
    elif modality == 'CR':
        sop_class_uid = CR_IMAGE_STORAGE_SOP_CLASS
    elif modality in ('DX', 'XQ'):
        sop_class_uid = DIGITAL_XRAY_IMAGE_STORAGE_SOP_CLASS
    else:
        sop_class_uid = SECONDARY_CAPTURE_SOP_CLASS

    acc_num = metadata.get('accession_number', '')
    sop_instance_uid = generate_uid()
    study_uid = metadata.get('study_instance_uid') or generate_deterministic_uid(f"STUDY_{acc_num}")
    series_uid = metadata.get('series_instance_uid') or generate_deterministic_uid(f"SERIES_{acc_num}_{metadata.get('series_number', 1)}")

    file_meta = _new_file_meta(sop_class_uid, sop_instance_uid)
    ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    _apply_common_metadata(ds, metadata, sop_class_uid, sop_instance_uid, study_uid, series_uid)

    ds.Modality = modality
    ds.ConversionType = 'WSD'
    ds.PatientOrientation = ['', '']
    ds.ImageType = ['DERIVED', 'SECONDARY']
    ds.LossyImageCompression = '00'

    ds.Rows = img.height
    ds.Columns = img.width
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PhotometricInterpretation = 'MONOCHROME2' if img.mode == 'L' else 'RGB'
    ds.SamplesPerPixel = 1 if img.mode == 'L' else 3
    if ds.SamplesPerPixel == 3:
        ds.PlanarConfiguration = 0

    pixel_bytes = img.tobytes()
    if len(pixel_bytes) % 2:
        pixel_bytes += b'\x00'
    ds.PixelData = pixel_bytes

    ds.save_as(output_path, write_like_original=False)
    return output_path, sop_instance_uid


def build_encapsulated_pdf(pdf_path, metadata, output_path):
    try:
        with open(pdf_path, 'rb') as f:
            pdf_bytes = f.read()
    except OSError as exc:
        raise DicomBuildError(f"Không đọc được PDF: {exc}") from exc
    if not pdf_bytes.startswith(b'%PDF'):
        raise DicomBuildError("File không phải PDF hợp lệ")

    acc_num = metadata.get('accession_number', '')
    sop_instance_uid = generate_uid()
    study_uid = metadata.get('study_instance_uid') or generate_deterministic_uid(f"STUDY_{acc_num}")
    series_uid = metadata.get('series_instance_uid') or generate_deterministic_uid(f"SERIES_{acc_num}_{metadata.get('series_number', 1)}")

    file_meta = _new_file_meta(ENCAPSULATED_PDF_SOP_CLASS, sop_instance_uid)
    ds = FileDataset(output_path, {}, file_meta=file_meta, preamble=b"\x00" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    _apply_common_metadata(ds, metadata, ENCAPSULATED_PDF_SOP_CLASS, sop_instance_uid, study_uid, series_uid)

    ds.Modality = metadata.get('modality', 'DOC')
    ds.ConversionType = 'WSD'
    ds.MIMETypeOfEncapsulatedDocument = 'application/pdf'
    ds.BurnedInAnnotation = 'YES'

    if len(pdf_bytes) % 2:
        pdf_bytes += b'\x00'
    ds.EncapsulatedDocument = pdf_bytes

    ds.save_as(output_path, write_like_original=False)
    return output_path, sop_instance_uid


def build_dicom_from_file(source_path, metadata, config):
    """Đóng gói file nguồn thành DICOM, lưu vào paths.dicom_staging_folder.
    Trả về (đường dẫn file .dcm, SOPInstanceUID)."""
    ext = os.path.splitext(source_path)[1].lower()
    filename_no_ext = os.path.splitext(os.path.basename(source_path))[0]
    output_dir = config['paths']['dicom_staging_folder']
    os.makedirs(output_dir, exist_ok=True)

    merged_metadata = dict(config['metadata'])
    merged_metadata.update(metadata)

    pid = str(merged_metadata.get('patient_id', '')).strip()
    acc = str(merged_metadata.get('accession_number', '')).strip()
    inst = str(merged_metadata.get('instance_number', 1)).zfill(3)

    if pid and pid != 'UNKNOWN':
        safe_pid = "".join(c for c in pid if c.isalnum()) or "PATIENT"
        safe_acc = "".join(c for c in acc if c.isalnum()) if (acc and acc != 'UNKNOWN') else "DOC"
        dicom_filename = f"{safe_pid}_{safe_acc}_{inst}.dcm"
    else:
        dicom_filename = filename_no_ext + '.dcm'

    output_path = os.path.join(output_dir, dicom_filename)

    if ext in ('.png', '.jpg', '.jpeg'):
        return build_secondary_capture_image(source_path, merged_metadata, output_path)
    elif ext == '.pdf':
        # Mặc định đóng gói PDF theo đúng chuẩn Encapsulated PDF (PRD mục 4.1).
        # Chỉ rasterize PDF thành ảnh Secondary Capture khi cấu hình bật tường minh
        # metadata.pdf_rasterize_to_image: true — dùng cho trường hợp PACS cụ thể
        # không hỗ trợ hiển thị Encapsulated PDF (chưa có bằng chứng xác nhận với
        # PACS hiện tại; GE Dicom Gateway Pro đẩy thành công cùng PACS này mà
        # không cần rasterize).
        if config.get('metadata', {}).get('pdf_rasterize_to_image', False):
            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(source_path)
                try:
                    if len(pdf) > 0:
                        page = pdf[0]
                        image = page.render(scale=3).to_pil()
                        temp_img_path = os.path.join(output_dir, f"temp_{filename_no_ext}.png")
                        image.save(temp_img_path)
                        try:
                            return build_secondary_capture_image(temp_img_path, merged_metadata, output_path)
                        finally:
                            if os.path.exists(temp_img_path):
                                os.remove(temp_img_path)
                finally:
                    # Đóng file handle native của pypdfium2 tới source_path — nếu không,
                    # trên Windows file gốc sẽ bị khóa (WinError 32) khi caller cố
                    # move/xóa file ngay sau khi build_dicom_from_file trả về.
                    pdf.close()
            except Exception:
                pass
        return build_encapsulated_pdf(source_path, merged_metadata, output_path)
    else:
        raise DicomBuildError(f"Định dạng không hỗ trợ: {ext}")

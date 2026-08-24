"""Hàm hỗ trợ: đọc/validate config, logging, kiểm tra file ổn định,
trích xuất metadata từ tên file, và registry chống xử lý trùng lặp."""
import hashlib
import logging
import logging.handlers
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

import yaml
from werkzeug.security import check_password_hash, generate_password_hash


class ConfigError(Exception):
    pass


REQUIRED_CONFIG_KEYS = {
    'pacs': ['ip', 'port', 'called_ae_title', 'calling_ae_title'],
    'watcher': ['watch_folders', 'stability_check_interval_sec', 'stability_check_count'],
    'paths': [
        'processed_folder', 'failed_folder', 'duplicates_folder',
        'dicom_staging_folder', 'retry_queue_folder', 'registry_db',
    ],
    'filename_pattern': ['regex', 'date_format'],
    'metadata': ['default_value', 'specific_character_set'],
    'retry': ['scan_interval_sec', 'backoff_schedule_sec', 'max_attempts'],
    'logging': ['log_folder', 'level', 'retention_days'],
}


def load_config(path):
    if not os.path.exists(path):
        raise ConfigError(f"Không tìm thấy file cấu hình: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ConfigError("File cấu hình rỗng hoặc sai định dạng YAML")
    _validate_config(config)
    return config


def save_config(config, path):
    """Lưu dict cấu hình vào file YAML với định dạng đẹp."""
    _validate_config(config)
    with open(path, 'w', encoding='utf-8') as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def get_watch_folders_list(config):
    """Chuẩn hoá watch_folders thành danh sách dict: [{'path': ..., 'modality': ...}]"""
    raw_folders = config.get('watcher', {}).get('watch_folders', [])
    result = []
    default_modality = config.get('metadata', {}).get('modality', 'OT')
    for item in raw_folders:
        if isinstance(item, str):
            result.append({'path': item, 'modality': default_modality})
        elif isinstance(item, dict):
            p = item.get('path', '')
            m = item.get('modality', default_modality)
            if p:
                result.append({'path': p, 'modality': m})
    return result


def _validate_config(config):
    missing = []
    for section, keys in REQUIRED_CONFIG_KEYS.items():
        if section not in config:
            missing.append(section)
            continue
        for key in keys:
            if key not in config[section]:
                missing.append(f"{section}.{key}")

    if 'ris' not in config:
        missing.append('ris')
    elif 'enabled' not in config['ris']:
        missing.append('ris.enabled')
    elif config['ris']['enabled']:
        for key in ('ip', 'port', 'called_ae_title', 'calling_ae_title'):
            if key not in config['ris']:
                missing.append(f"ris.{key}")

    if missing:
        raise ConfigError("Thiếu tham số cấu hình bắt buộc: " + ", ".join(missing))

    folders = get_watch_folders_list(config)
    if not folders:
        raise ConfigError("watcher.watch_folders không được rỗng")
    if not config['retry']['backoff_schedule_sec']:
        raise ConfigError("retry.backoff_schedule_sec không được rỗng")

    for ae_field in ('called_ae_title', 'calling_ae_title'):
        if len(config['pacs'].get(ae_field, '')) > 16:
            raise ConfigError(f"pacs.{ae_field} '{config['pacs'][ae_field]}' không được vượt quá 16 ký tự")
        if config['ris'].get('enabled', False) and len(config['ris'].get(ae_field, '')) > 16:
            raise ConfigError(f"ris.{ae_field} '{config['ris'][ae_field]}' không được vượt quá 16 ký tự")

    try:
        re.compile(config['filename_pattern']['regex'])
    except re.error as exc:
        raise ConfigError(f"filename_pattern.regex không hợp lệ: {exc}")


def get_system_stats(config):
    """Đếm số lượng file trong các thư mục chính."""
    paths = config.get('paths', {})
    def _count_files(folder_path, ext=None):
        if not os.path.exists(folder_path):
            return 0
        count = 0
        for entry in os.scandir(folder_path):
            if entry.is_file():
                if ext is None or entry.name.lower().endswith(ext):
                    count += 1
        return count

    return {
        'processed_count': _count_files(paths.get('processed_folder', '')),
        'retry_count': _count_files(paths.get('retry_queue_folder', ''), ext='.dcm'),
        'failed_count': _count_files(paths.get('failed_folder', '')),
        'duplicates_count': _count_files(paths.get('duplicates_folder', '')),
    }


def test_ris_connection(ris_config):
    """Thực hiện C-ECHO tới RIS Server để kiểm tra kết nối."""
    if not ris_config.get('enabled', False):
        return False, "RIS đang bị tắt (enabled: false)"
    from pynetdicom import AE
    from pynetdicom.sop_class import Verification
    ae = AE(ae_title=ris_config.get('calling_ae_title', 'DICOM_GATEWAY'))
    ae.add_requested_context(Verification)
    timeout = ris_config.get('connect_timeout_sec', 10)
    ae.acse_timeout = timeout
    ae.network_timeout = timeout
    ae.dimse_timeout = timeout
    try:
        assoc = ae.associate(
            ris_config['ip'],
            int(ris_config['port']),
            ae_title=ris_config['called_ae_title']
        )
        if assoc.is_established:
            status = assoc.send_c_echo()
            assoc.release()
            if status and status.Status == 0:
                return True, "Kết nối C-ECHO RIS thành công"
            return False, f"C-ECHO RIS thất bại với status code: {hex(status.Status) if status else 'None'}"
        return False, "Không thể kết nối đến RIS Server (Association rejected/timed out)"
    except Exception as exc:
        return False, f"Lỗi kết nối RIS: {exc}"



def setup_logging(config):
    log_cfg = config['logging']
    os.makedirs(log_cfg['log_folder'], exist_ok=True)
    log_path = os.path.join(log_cfg['log_folder'], 'gateway.log')

    logger = logging.getLogger('dicom_gateway')
    logger.setLevel(getattr(logging, log_cfg.get('level', 'INFO').upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when='midnight', backupCount=log_cfg.get('retention_days', 90), encoding='utf-8'
    )
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def wait_for_stable_file(path, interval_sec, required_stable_checks, timeout_sec=300):
    """Chờ tới khi kích thước file không đổi qua `required_stable_checks` lần đo
    liên tiếp, nghĩa là thiết bị đã ghi xong. Trả về False nếu file biến mất
    hoặc không ổn định trước khi hết timeout."""
    stable_count = 0
    last_size = -1
    start = time.monotonic()
    while time.monotonic() - start < timeout_sec:
        if not os.path.exists(path):
            return False
        try:
            size = os.path.getsize(path)
        except OSError:
            stable_count = 0
            time.sleep(interval_sec)
            continue
        if size == last_size and size > 0:
            stable_count += 1
            if stable_count >= required_stable_checks:
                return True
        else:
            stable_count = 0
        last_size = size
        time.sleep(interval_sec)
    return False


def extract_metadata_from_filename(filename, pattern_config, default_value):
    """Trích metadata từ tên file theo regex cấu hình. Nếu không khớp regex chính,
    sử dụng cơ chế phân tích dự phòng theo ký tự phân cách (-/_) để cố gắng
    lấy PatientID, giúp tra cứu RIS Worklist chính xác thay vì dùng 'UNKNOWN'."""
    warnings = []
    name_without_ext = os.path.splitext(filename)[0]
    regex = pattern_config['regex']
    date_format = pattern_config['date_format']

    match = re.match(regex, name_without_ext)
    groups = match.groupdict() if match else {}
    if not match:
        warnings.append("Tên file không khớp mẫu quy định, dùng phân tích dự phòng")
        parts = [p.strip() for p in re.split(r'[-_]', name_without_ext) if p.strip()]
        if len(parts) >= 1 and any(c.isdigit() for c in parts[0]):
            groups['patient_id'] = parts[0]
            remaining = parts[1:]
            # Lấy phần đầu tiên KHÔNG phải toàn số làm PatientName — bỏ qua các mã
            # số xen giữa (VD năm sinh/mã nội bộ '1961' trong
            # '2200857_1961_Tieu Thi Van Ha_...').
            name_part = next((p for p in remaining if not p.isdigit()), None)
            if name_part:
                groups['patient_name'] = name_part
            # Chỉ nhận StudyDate nếu CHỈ CÓ ĐÚNG MỘT chuỗi 8 số trong tên file. Nếu
            # có nhiều hơn 1 (không rõ cái nào là ngày chỉ định thật, ví dụ tên file
            # có cả ngày chỉ định lẫn ngày xuất file), để trống thay vì đoán sai —
            # build_dicom_from_file sẽ tự dùng ngày hôm nay, an toàn hơn nhiều so
            # với gán nhầm StudyDate khiến ca khám "biến mất" trên PACS do lệch bộ lọc.
            date_candidates = [p for p in remaining if re.match(r'^\d{8}$', p)]
            if len(date_candidates) == 1:
                groups['study_date'] = date_candidates[0]
            elif len(date_candidates) > 1:
                warnings.append(
                    f"Tên file có nhiều chuỗi ngày mơ hồ {date_candidates}, "
                    f"không thể xác định StudyDate chắc chắn — để trống, dùng ngày hôm nay"
                )

    patient_id = groups.get('patient_id') or default_value
    if not groups.get('patient_id'):
        warnings.append("Không trích xuất được PatientID từ tên file")

    patient_name = groups.get('patient_name') or default_value
    if not groups.get('patient_name'):
        warnings.append("Không trích xuất được PatientName từ tên file")
    else:
        patient_name = ' '.join(str(patient_name).replace('^', ' ').replace('_', ' ').split())

    raw_date = groups.get('study_date')
    study_date = ''
    if raw_date:
        try:
            parsed = datetime.strptime(raw_date, date_format)
            study_date = parsed.strftime('%Y%m%d')
        except ValueError:
            warnings.append(f"StudyDate '{raw_date}' không đúng định dạng {date_format}, để trống")
    else:
        warnings.append("Không trích xuất được StudyDate từ tên file, để trống")

    metadata = {
        'patient_id': patient_id,
        'patient_name': patient_name,
        'study_date': study_date,
        'accession_number': default_value,
        'default_value': default_value,
    }
    return metadata, warnings


def merge_ris_metadata(metadata, ris_data):
    """Ghi đè metadata trích từ tên file bằng dữ liệu tra cứu được từ RIS
    (PatientName, PatientBirthDate, PatientSex, AccessionNumber, StudyInstanceUID, StudyDescription),
    vì RIS là nguồn thông tin hành chính đáng tin cậy hơn tên file. Chỉ ghi đè các
    trường RIS thực sự trả về giá trị; giữ nguyên phần còn lại nếu RIS
    không có hoặc không tìm thấy bệnh nhân."""
    if not ris_data:
        return metadata
    merged = dict(metadata)
    for key in ('patient_name', 'patient_birth_date', 'patient_sex', 'accession_number', 'study_instance_uid', 'study_description'):
        value = ris_data.get(key)
        if value:
            if key == 'patient_name':
                value = ' '.join(str(value).replace('^', ' ').replace('_', ' ').split())
            merged[key] = value
    return merged


def compute_file_hash(path, chunk_size=65536):
    hasher = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def dedupe_destination(dest_path):
    """Nếu dest_path đã tồn tại, sinh tên mới không trùng (thêm hậu tố _1, _2...)."""
    if not os.path.exists(dest_path):
        return dest_path
    base, ext = os.path.splitext(dest_path)
    counter = 1
    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


class ProcessedRegistry:
    """Registry SQLite chống gửi trùng & quản lý nhật ký lịch sử ca chụp."""

    def __init__(self, db_path):
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_hash TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    sop_instance_uid TEXT,
                    processed_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS studies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_hash TEXT,
                    filename TEXT NOT NULL,
                    patient_id TEXT,
                    patient_name TEXT,
                    study_date TEXT,
                    accession_number TEXT,
                    study_description TEXT,
                    modality TEXT,
                    sop_instance_uid TEXT,
                    status TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def is_processed(self, file_hash):
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM processed_files WHERE file_hash = ?", (file_hash,)
            )
            return cur.fetchone() is not None

    def mark_processed(self, file_hash, original_filename, sop_instance_uid):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO processed_files "
                "(file_hash, original_filename, sop_instance_uid, processed_at) VALUES (?, ?, ?, ?)",
                (file_hash, original_filename, sop_instance_uid, datetime.now().isoformat()),
            )
            self._conn.commit()

    def record_study(self, filename, metadata, status, sop_instance_uid=None, file_hash=None, last_error=None):
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO studies 
                (file_hash, filename, patient_id, patient_name, study_date, accession_number, study_description, modality, sop_instance_uid, status, last_error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_hash,
                    filename,
                    metadata.get('patient_id', ''),
                    metadata.get('patient_name', ''),
                    metadata.get('study_date', ''),
                    metadata.get('accession_number', ''),
                    metadata.get('study_description', ''),
                    metadata.get('modality', ''),
                    sop_instance_uid,
                    status,
                    last_error,
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def get_studies(self, status_filter=None, search_keyword=None, limit=100):
        with self._lock:
            sql = "SELECT * FROM studies WHERE 1=1"
            params = []
            if status_filter and status_filter != 'ALL':
                sql += " AND status = ?"
                params.append(status_filter)
            if search_keyword:
                kw = f"%{search_keyword}%"
                sql += " AND (patient_id LIKE ? OR patient_name LIKE ? OR accession_number LIKE ? OR filename LIKE ?)"
                params.extend([kw, kw, kw, kw])
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)

            cur = self._conn.execute(sql, params)
            rows = cur.fetchall()
            return [dict(row) for row in rows]

    def get_modality_stats(self, date_str=None):
        """Tổng hợp thống kê theo từng Modality (tổng ca, thành công, retry, lỗi, lần hoạt động cuối)."""
        import re
        if not date_str:
            today_date = datetime.now().strftime('%Y%m%d')
            today_iso = datetime.now().strftime('%Y-%m-%d')
        else:
            clean_date = re.sub(r'\D', '', str(date_str))
            today_date = clean_date if len(clean_date) == 8 else date_str
            today_iso = f"{clean_date[:4]}-{clean_date[4:6]}-{clean_date[6:8]}" if len(clean_date) == 8 else date_str

        with self._lock:
            # Lấy thống kê hôm nay
            sql_today = """
                SELECT 
                    COALESCE(NULLIF(UPPER(TRIM(modality)), ''), 'OT') as mod_code,
                    status,
                    COUNT(*) as count,
                    MAX(created_at) as last_seen
                FROM studies
                WHERE study_date = ? OR created_at LIKE ?
                GROUP BY mod_code, status
            """
            cur = self._conn.execute(sql_today, (today_date, f"{today_iso}%"))
            rows_today = cur.fetchall()

            # Lấy thống kê toàn thời gian (All-Time)
            sql_all = """
                SELECT 
                    COALESCE(NULLIF(UPPER(TRIM(modality)), ''), 'OT') as mod_code,
                    status,
                    COUNT(*) as count,
                    MAX(created_at) as last_seen
                FROM studies
                GROUP BY mod_code, status
            """
            cur = self._conn.execute(sql_all)
            rows_all = cur.fetchall()

            # Lấy ca chụp gần nhất của từng modality
            sql_recent = """
                SELECT 
                    s1.id, s1.modality, s1.patient_id, s1.patient_name, s1.accession_number,
                    s1.study_description, s1.status, s1.created_at
                FROM studies s1
                INNER JOIN (
                    SELECT COALESCE(NULLIF(UPPER(TRIM(modality)), ''), 'OT') as mod_code, MAX(id) as max_id
                    FROM studies
                    GROUP BY mod_code
                ) s2 ON s1.id = s2.max_id
            """
            cur = self._conn.execute(sql_recent)
            rows_recent = cur.fetchall()

            stats = {}

            def _get_entry(code):
                if code not in stats:
                    stats[code] = {
                        'modality': code,
                        'today': {'total': 0, 'success': 0, 'retrying': 0, 'failed': 0, 'duplicate': 0},
                        'all_time': {'total': 0, 'success': 0, 'retrying': 0, 'failed': 0, 'duplicate': 0},
                        'last_activity': None,
                        'last_patient': None,
                    }
                return stats[code]

            for r in rows_today:
                code = r['mod_code']
                status = str(r['status']).upper()
                cnt = r['count']
                entry = _get_entry(code)
                entry['today']['total'] += cnt
                if status == 'SUCCESS':
                    entry['today']['success'] += cnt
                elif status == 'RETRYING':
                    entry['today']['retrying'] += cnt
                elif status == 'FAILED':
                    entry['today']['failed'] += cnt
                elif status == 'DUPLICATE':
                    entry['today']['duplicate'] += cnt

                if r['last_seen'] and (not entry['last_activity'] or r['last_seen'] > entry['last_activity']):
                    entry['last_activity'] = r['last_seen']

            for r in rows_all:
                code = r['mod_code']
                status = str(r['status']).upper()
                cnt = r['count']
                entry = _get_entry(code)
                entry['all_time']['total'] += cnt
                if status == 'SUCCESS':
                    entry['all_time']['success'] += cnt
                elif status == 'RETRYING':
                    entry['all_time']['retrying'] += cnt
                elif status == 'FAILED':
                    entry['all_time']['failed'] += cnt
                elif status == 'DUPLICATE':
                    entry['all_time']['duplicate'] += cnt

                if r['last_seen'] and (not entry['last_activity'] or r['last_seen'] > entry['last_activity']):
                    entry['last_activity'] = r['last_seen']

            for r in rows_recent:
                code = (r['modality'] or 'OT').strip().upper() or 'OT'
                entry = _get_entry(code)
                entry['last_patient'] = {
                    'patient_id': r['patient_id'],
                    'patient_name': r['patient_name'],
                    'accession_number': r['accession_number'],
                    'study_description': r['study_description'],
                    'status': r['status'],
                    'created_at': r['created_at'],
                }

            return stats

    def close(self):
        with self._lock:
            self._conn.close()


def hash_password(password: str) -> str:
    """Tạo chuỗi băm mật khẩu an toàn."""
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Kiểm tra mật khẩu nhập vào khớp với password_hash."""
    if not password_hash or not password:
        return False
    return check_password_hash(password_hash, password)


def get_auth_config(config: dict) -> dict:
    """Lấy cấu hình auth, tự khởi tạo nếu chưa có."""
    if not config:
        return {'enabled': False, 'users': []}
    return config.get('auth', {'enabled': False, 'users': []})


def get_user_by_username(config: dict, username: str) -> dict | None:
    """Tìm thông tin tài khoản theo username."""
    auth = get_auth_config(config)
    users = auth.get('users', [])
    for u in users:
        if u.get('username', '').lower() == (username or '').strip().lower():
            return u
    return None


def authenticate_user(config: dict, username: str, password: str) -> dict | None:
    """Xác thực tài khoản và mật khẩu, trả về thông tin an toàn (bỏ hash)."""
    user = get_user_by_username(config, username)
    if not user:
        return None
    if not verify_password(password, user.get('password_hash', '')):
        return None
    return {
        'username': user.get('username'),
        'full_name': user.get('full_name', user.get('username')),
        'department': user.get('department', ''),
        'role': user.get('role', 'TECHNICIAN'),
        'allowed_modalities': user.get('allowed_modalities', []),
    }


def list_users(config: dict) -> list[dict]:
    """Trả về danh sách tất cả người dùng (không bao gồm password_hash)."""
    auth = get_auth_config(config)
    users = auth.get('users', [])
    clean_list = []
    for u in users:
        clean_list.append({
            'username': u.get('username'),
            'full_name': u.get('full_name', ''),
            'department': u.get('department', ''),
            'role': u.get('role', 'TECHNICIAN'),
            'allowed_modalities': u.get('allowed_modalities', []),
        })
    return clean_list


def update_user_password(config: dict, config_path: str, username: str, new_password: str) -> bool:
    """Cập nhật mật khẩu mới cho tài khoản."""
    user = get_user_by_username(config, username)
    if not user:
        return False
    user['password_hash'] = hash_password(new_password)
    save_config(config, config_path)
    return True


def upsert_user(config: dict, config_path: str, user_data: dict) -> dict:
    """Thêm mới hoặc cập nhật thông tin tài khoản."""
    if 'auth' not in config:
        config['auth'] = {'enabled': True, 'users': []}
    if 'users' not in config['auth']:
        config['auth']['users'] = []

    username = (user_data.get('username') or '').strip()
    if not username:
        raise ValueError("Tên đăng nhập (username) không được để trống")

    existing = get_user_by_username(config, username)
    if existing:
        if user_data.get('full_name') is not None:
            existing['full_name'] = user_data['full_name']
        if user_data.get('department') is not None:
            existing['department'] = user_data['department']
        if user_data.get('role') is not None:
            existing['role'] = user_data['role']
        if user_data.get('allowed_modalities') is not None:
            existing['allowed_modalities'] = user_data['allowed_modalities']
        if user_data.get('password'):
            existing['password_hash'] = hash_password(user_data['password'])
    else:
        password = user_data.get('password') or '123456'
        new_u = {
            'username': username,
            'password_hash': hash_password(password),
            'full_name': user_data.get('full_name', username),
            'department': user_data.get('department', ''),
            'role': user_data.get('role', 'TECHNICIAN'),
            'allowed_modalities': user_data.get('allowed_modalities', []),
        }
        config['auth']['users'].append(new_u)

    save_config(config, config_path)
    return get_user_by_username(config, username)


def delete_user(config: dict, config_path: str, username: str) -> bool:
    """Xóa tài khoản khỏi danh sách (chặn xóa tài khoản admin cuối cùng)."""
    auth = get_auth_config(config)
    users = auth.get('users', [])
    target = None
    admin_count = 0
    for u in users:
        if u.get('role') == 'ADMIN':
            admin_count += 1
        if u.get('username', '').lower() == (username or '').strip().lower():
            target = u

    if not target:
        return False
    if target.get('role') == 'ADMIN' and admin_count <= 1:
        raise ValueError("Không thể xóa tài khoản Admin duy nhất của hệ thống")

    users.remove(target)
    save_config(config, config_path)
    return True


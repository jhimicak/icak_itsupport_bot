from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import requests
import os
from datetime import datetime, timedelta, timezone
import uuid
import re
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import base64
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
CORS(app)

# 환경 변수 설정
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'

# Google Sheets 설정
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')

# 파일 업로드 설정
UPLOAD_FOLDER = '/tmp/uploads'  # Render에서는 /tmp 사용
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# FAQ 데이터 및 설정
FAQ_DATA = {
    '영업시간': '평일 09:00 - 18:00 (주말 및 공휴일 휴무)',
    '위치': '서울시 강남구 테헤란로 123',
    '연락처': '02-1234-5678',
    '이메일': 'contact@example.com',
    '상담': '상담원 연결을 원하시면 "상담원"을 입력해주세요.',
    '근애': '김근애 고생많았어요',
    '현경': '켠경은 좀 더 고생해요',
}

ADMIN_KEYWORDS = ['상담원']
SESSION_TIMEOUT_MINUTES = 10

# 저장소
user_sessions = {}
admin_responses = {}
active_consultations = {}
topic_ids = {}
greeted_users = set()  # 인사 메시지를 보낸 사용자 추적

# Google Sheets 클라이언트 초기화
google_sheets_client = None

def init_google_sheets():
    """Google Sheets API 초기화"""
    global google_sheets_client
    
    try:
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        
        if not creds_json:
            print("⚠️ GOOGLE_SHEETS_CREDENTIALS 환경 변수가 없습니다.")
            return None
        
        creds_dict = json.loads(creds_json)
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        google_sheets_client = gspread.authorize(credentials)
        
        print("✅ Google Sheets 연결 성공!")
        return google_sheets_client
        
    except Exception as e:
        print(f"❌ Google Sheets 초기화 실패: {e}")
        return None

init_google_sheets()

# --- 파일 처리 함수 ---

def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_image(filename):
    """이미지 파일인지 확인"""
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in {'png', 'jpg', 'jpeg', 'gif'}

def is_video(filename):
    """비디오 파일인지 확인"""
    ext = filename.rsplit('.', 1)[1].lower()
    return ext in {'mp4', 'mov', 'avi'}

# --- Google Sheets 저장 함수 ---

def get_or_create_sheet(user_id):
    """사용자별 시트 가져오기 또는 생성"""
    if not google_sheets_client or not GOOGLE_SHEET_ID:
        return None
    
    try:
        spreadsheet = google_sheets_client.open_by_key(GOOGLE_SHEET_ID)
        sheet_name = f"User_{user_id}"
        
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
            worksheet.append_row([
                '타임스탬프', '날짜', '시간', '발신자', 
                '메시지 타입', '메시지 내용', '세션 ID'
            ])
            worksheet.format('A1:G1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.4, 'green': 0.5, 'blue': 0.9}
            })
        
        return worksheet
        
    except Exception as e:
        print(f"❌ 시트 가져오기 실패: {e}")
        return None

def save_to_google_sheets(user_id, message_type, message_content, sender='user'):
    """Google Sheets에 대화 내용 저장"""
    worksheet = get_or_create_sheet(user_id)
    
    if not worksheet:
        print("⚠️ Google Sheets에 저장 실패")
        return False
    
    try:
        now = kst_now()
        timestamp = now.isoformat()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        session_id = ""
        if user_id in active_consultations:
            session_id = active_consultations[user_id]['start_time'].strftime('%Y%m%d_%H%M%S')
        
        sender_name = {
            'user': '사용자',
            'bot': '챗봇',
            'admin': '상담원',
            'system': '시스템'
        }.get(sender, sender)
        
        worksheet.append_row([
            timestamp, date_str, time_str,
            sender_name, message_type, message_content, session_id
        ])
        
        print(f"✅ Google Sheets에 저장 완료: {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ Google Sheets 저장 실패: {e}")
        return False

def save_session_summary(user_id, start_time, end_time, reason):
    """상담 세션 요약 저장"""
    if not google_sheets_client or not GOOGLE_SHEET_ID:
        return
    
    try:
        spreadsheet = google_sheets_client.open_by_key(GOOGLE_SHEET_ID)
        
        try:
            summary_sheet = spreadsheet.worksheet("SessionSummary")
        except gspread.exceptions.WorksheetNotFound:
            summary_sheet = spreadsheet.add_worksheet(title="SessionSummary", rows=1000, cols=8)
            summary_sheet.append_row([
                '사용자 ID', '세션 시작', '세션 종료', '지속 시간 (초)',
                '종료 사유', '날짜', '시작 시간', '종료 시간'
            ])
            summary_sheet.format('A1:H1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.6, 'blue': 0.4}
            })
        
        duration = (end_time - start_time).total_seconds()
        date_str = start_time.strftime('%Y-%m-%d')
        start_time_str = start_time.strftime('%H:%M:%S')
        end_time_str = end_time.strftime('%H:%M:%S')
        
        reason_text = {
            'manual': '사용자 요청',
            'timeout': '타임아웃',
            'admin': '관리자 종료'
        }.get(reason, reason)
        
        summary_sheet.append_row([
            user_id, start_time.isoformat(), end_time.isoformat(),
            int(duration), reason_text, date_str, start_time_str, end_time_str
        ])
        
        print(f"✅ 세션 요약 저장 완료: {user_id}")
        
    except Exception as e:
        print(f"❌ 세션 요약 저장 실패: {e}")

# --- 상담 세션 관리 함수 ---

def kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)

def start_consultation_session(user_id):
    """상담 세션 시작"""
    active_consultations[user_id] = {
        'start_time': kst_now(),
        'last_activity': kst_now()
    }
    save_to_google_sheets(user_id, 'system', '상담 세션 시작', 'system')

def update_session_activity(user_id):
    """세션 활동 시간 업데이트"""
    if user_id in active_consultations:
        active_consultations[user_id]['last_activity'] = kst_now()

def is_session_active(user_id):
    """세션이 활성화되어 있는지 확인"""
    if user_id not in active_consultations:
        return False
    
    last_activity = active_consultations[user_id]['last_activity']
    timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    
    if kst_now() - last_activity > timeout:
        end_consultation_session(user_id, 'timeout')
        return False
    
    return True

def end_consultation_session(user_id, reason='manual'):
    """상담 세션 종료"""
    if user_id in active_consultations:
        session_info = active_consultations[user_id]
        start_time = session_info['start_time']
        end_time = kst_now()
        duration = end_time - start_time
        
        end_message = f"상담 세션 종료 (사유: {reason}, 지속시간: {str(duration).split('.')[0]})"
        save_to_google_sheets(user_id, 'system', end_message, 'system')
        save_session_summary(user_id, start_time, end_time, reason)
        
        del active_consultations[user_id]
        notify_admin_session_end(user_id, reason, duration)

def notify_admin_session_end(user_id, reason, duration):
    """관리자에게 세션 종료 알림"""
    reason_text = {
        'manual': '사용자 요청',
        'timeout': '타임아웃 (10분 무응답)',
        'admin': '관리자 종료'
    }.get(reason, reason)
    
    message = (
        f"✅ <b>상담 세션 종료</b>\n\n"
        f"USER_ID: [{user_id}]\n"
        f"종료 사유: {reason_text}\n"
        f"상담 시간: {str(duration).split('.')[0]}\n"
        f"⏰ {kst_now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram_message(ADMIN_CHAT_ID, message)

# --- 텔레그램 함수 ---

def get_telegram_file_url(file_id):
    """텔레그램 파일 ID로 다운로드 URL 가져오기"""
    try:
        url = f'{TELEGRAM_API_URL}/getFile'
        response = requests.get(url, params={'file_id': file_id})
        result = response.json()
        
        if result.get('ok'):
            file_path = result['result']['file_path']
            file_url = f'https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}'
            return file_url
        else:
            print(f"파일 URL 가져오기 실패: {result}")
            return None
    except Exception as e:
        print(f"파일 URL 가져오기 에러: {e}")
        return None

def send_telegram_message(chat_id, text, thread_id=None):
    """텔레그램 메시지 발송"""
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    if thread_id:
        data['message_thread_id'] = thread_id
    
    try:
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")
        return None

def send_telegram_photo(chat_id, photo_data, caption=None, thread_id=None):
    """텔레그램 사진 발송"""
    url = f'{TELEGRAM_API_URL}/sendPhoto'
    files = {'photo': photo_data}
    data = {'chat_id': chat_id}
    if caption:
        data['caption'] = caption
        data['parse_mode'] = 'HTML'
    if thread_id:
        data['message_thread_id'] = thread_id
    
    try:
        response = requests.post(url, data=data, files=files)
        return response.json()
    except Exception as e:
        print(f"텔레그램 사진 전송 에러: {e}")
        return None

def send_telegram_video(chat_id, video_data, caption=None, thread_id=None):
    """텔레그램 비디오 발송"""
    url = f'{TELEGRAM_API_URL}/sendVideo'
    files = {'video': video_data}
    data = {'chat_id': chat_id}
    if caption:
        data['caption'] = caption
        data['parse_mode'] = 'HTML'
    if thread_id:
        data['message_thread_id'] = thread_id
    
    try:
        response = requests.post(url, data=data, files=files)
        return response.json()
    except Exception as e:
        print(f"텔레그램 비디오 전송 에러: {e}")
        return None

def create_telegram_topic(user_id):
    """텔레그램 그룹 내에 유저 전용 주제(Topic) 생성"""
    if user_id in topic_ids:
        return topic_ids[user_id]

    url = f'{TELEGRAM_API_URL}/createForumTopic'
    payload = {'chat_id': ADMIN_CHAT_ID, 'name': f"상담: {user_id}"}
    
    try:
        response = requests.post(url, json=payload).json()
        if response.get('ok'):
            thread_id = response['result']['message_thread_id']
            topic_ids[user_id] = thread_id
            return thread_id
        else:
            print(f"Topic 생성 실패: {response}")
            return None
    except Exception as e:
        print(f"Topic 생성 에러: {e}")
        return None

def notify_admin(user_id, user_message):
    """새 상담 요청 시 Topic을 생성하고 알림"""
    thread_id = create_telegram_topic(user_id)
    timestamp = kst_now().strftime('%Y-%m-%d %H:%M:%S')
    
    message = (
        f"🔔 <b>새 상담 요청</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💬 내용: {user_message}\n"
        f"⏰ 시간: {timestamp}\n"
        f"━━━━━━━━━━━━━━\n"
        f"<b>이곳에서 대화를 시작하세요.</b>"
    )
    
    return send_telegram_message(ADMIN_CHAT_ID, message, thread_id)

def notify_admin_message(user_id, user_message):
    """특정 유저의 Topic 방으로 메시지 전송"""
    thread_id = create_telegram_topic(user_id)
    
    message = (
        f"👤 <b>유저 메시지</b>\n\n"
        f"{user_message}\n\n"
        f"⏰ {kst_now().strftime('%H:%M:%S')}\n"
        f"ID: [{user_id}]"
    )
    
    return send_telegram_message(ADMIN_CHAT_ID, message, thread_id)

def notify_admin_file(user_id, file_path, file_type, original_filename):
    """파일을 텔레그램으로 전송"""
    thread_id = create_telegram_topic(user_id)
    caption = f"👤 유저가 파일을 보냈습니다\n파일명: {original_filename}\n⏰ {kst_now().strftime('%H:%M:%S')}\nID: [{user_id}]"
    
    try:
        with open(file_path, 'rb') as f:
            if file_type == 'image':
                return send_telegram_photo(ADMIN_CHAT_ID, f, caption, thread_id)
            elif file_type == 'video':
                return send_telegram_video(ADMIN_CHAT_ID, f, caption, thread_id)
    except Exception as e:
        print(f"파일 전송 실패: {e}")
        return None

def find_faq_answer(message):
    """FAQ 데이터에서 키워드 매칭"""
    message_lower = message.lower().replace(" ", "")
    for keyword, answer in FAQ_DATA.items():
        if keyword in message_lower:
            return answer
    return None

# --- 라우트 (API) ---

@app.route('/')
def index():
    """챗봇 웹페이지"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())[:8]
    return render_template('chatbot.html')

@app.route('/api/greeting', methods=['GET'])
def greeting():
    """첫 접속 시 인사 메시지"""
    user_id = session.get('user_id')
    
    if user_id not in greeted_users:
        greeted_users.add(user_id)
        greeting_message = (
            "안녕하세요! 해외건설협회 상담 챗봇입니다. 😊\n\n"
            "궁금하신 사항을 자유롭게 물어보세요.\n"
            "직원과 상담을 원하시면 '상담원'을 입력해주세요."
        )
        save_to_google_sheets(user_id, 'greeting', greeting_message, 'bot')
        return jsonify({
            'has_greeting': True,
            'message': greeting_message,
            'timestamp': kst_now().isoformat()
        })
    
    return jsonify({'has_greeting': False})

@app.route('/api/chat', methods=['POST'])
def chat():
    """채팅 API 엔드포인트"""
    data = request.json
    user_message = data.get('message', '').strip()
    user_id = session.get('user_id', 'unknown')

    if not user_message:
        return jsonify({'error': '메시지를 입력해주세요'}), 400

    save_to_google_sheets(user_id, 'user_message', user_message, 'user')

    # 상담 종료 체크
    if user_message in ['상담종료', '상담 종료', '종료']:
        if is_session_active(user_id):
            end_consultation_session(user_id, 'manual')
            response_text = '상담이 종료되었습니다. 이용해주셔서 감사합니다.\n\n다시 상담을 원하시면 "상담원"을 입력해주세요.'
            save_to_google_sheets(user_id, 'system', response_text, 'bot')
            return jsonify({
                'type': 'session_end',
                'message': response_text,
                'timestamp': kst_now().isoformat()
            })
        else:
            response_text = '활성화된 상담 세션이 없습니다.'
            save_to_google_sheets(user_id, 'default', response_text, 'bot')
            return jsonify({
                'type': 'error',
                'message': response_text,
                'timestamp': kst_now().isoformat()
            })

    # 활성 상담 세션
    if is_session_active(user_id):
        update_session_activity(user_id)
        notify_admin_message(user_id, user_message)
        save_to_google_sheets(user_id, 'consultation', user_message, 'user')
        
        return jsonify({
            'type': 'consultation_active',
            'message': '',
            'timestamp': kst_now().isoformat()
        })

    # 상담원 연결 요청
    if any(k in user_message for k in ADMIN_KEYWORDS):
        start_consultation_session(user_id)
        notify_admin(user_id, user_message)
        
        response_text = (
            '✅ 상담원과 연결되었습니다.\n\n'
            '이제 입력하시는 모든 메시지가 상담원에게 전달됩니다.\n'
            '상담을 종료하시려면 "상담종료"를 입력해주세요.\n\n'
            f'(세션은 {SESSION_TIMEOUT_MINUTES}분간 유지됩니다)'
        )
        save_to_google_sheets(user_id, 'admin_request', response_text, 'bot')
        
        return jsonify({
            'type': 'session_start',
            'message': response_text,
            'timestamp': kst_now().isoformat()
        })

    # FAQ 자동 응답
    faq_answer = find_faq_answer(user_message)
    if faq_answer:
        save_to_google_sheets(user_id, 'faq', faq_answer, 'bot')
        return jsonify({
            'type': 'faq',
            'message': faq_answer,
            'timestamp': kst_now().isoformat()
        })

    # 기본 응답
    response_text = (
        "죄송합니다. 정확한 답변을 찾지 못했습니다.\n\n"
        "도움말 키워드: 영업시간, 위치, 연락처, 이메일\n\n"
        "직원과 대화를 원하시면 '상담원'이라고 입력해주세요."
    )
    save_to_google_sheets(user_id, 'default', response_text, 'bot')
    
    return jsonify({
        'type': 'default',
        'message': response_text,
        'timestamp': kst_now().isoformat()
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """파일 업로드 처리"""
    user_id = session.get('user_id', 'unknown')
    
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': '파일이 선택되지 않았습니다'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': '지원하지 않는 파일 형식입니다'}), 400
    
    # 세션 활성화 체크
    if not is_session_active(user_id):
        return jsonify({'error': '상담원과 연결된 상태에서만 파일을 보낼 수 있습니다'}), 403
    
    try:
        # 파일 저장
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, f"{user_id}_{kst_now().timestamp()}_{filename}")
        file.save(filepath)
        
        # 파일 타입 확인
        file_type = 'image' if is_image(filename) else 'video'
        
        # 텔레그램으로 전송
        result = notify_admin_file(user_id, filepath, file_type, filename)
        
        # 로그 저장
        save_to_google_sheets(user_id, 'file_upload', f'[{file_type.upper()}] {filename}', 'user')
        
        # 임시 파일 삭제
        if os.path.exists(filepath):
            os.remove(filepath)
        
        update_session_activity(user_id)
        
        return jsonify({
            'success': True,
            'message': f'{file_type} 파일이 상담원에게 전송되었습니다',
            'timestamp': kst_now().isoformat()
        })
        
    except Exception as e:
        print(f"파일 업로드 에러: {e}")
        return jsonify({'error': '파일 업로드 중 오류가 발생했습니다'}), 500

@app.route('/api/check_reply', methods=['GET'])
def check_reply():
    """관리자 답변 확인 - 텍스트 및 미디어 포함"""
    user_id = session.get('user_id')
    
    if user_id in admin_responses and admin_responses[user_id]:
        reply_data = admin_responses[user_id].pop(0)
        
        # 텍스트인 경우
        if isinstance(reply_data, str):
            reply_data = {'type': 'text', 'content': reply_data}
        
        # Google Sheets 저장은 웹훅에서 이미 처리됨
        
        # 세션 활동 업데이트
        if is_session_active(user_id):
            update_session_activity(user_id)
        
        return jsonify({'has_reply': True, 'data': reply_data})
    
    return jsonify({'has_reply': False})

@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    """텔레그램 웹훅 - 텍스트 및 미디어 처리"""
    data = request.json
    
    if 'message' in data:
        msg = data['message']
        thread_id = msg.get('message_thread_id')
        
        # 봇 자신의 메시지는 무시
        if msg.get('from', {}).get('is_bot'):
            return jsonify({'status': 'ok'})
        
        # 어느 사용자의 Topic인지 확인
        target_user_id = next((uid for uid, tid in topic_ids.items() if tid == thread_id), None)
        
        if not target_user_id:
            return jsonify({'status': 'ok'})
        
        # 세션 활성화 확인
        if not is_session_active(target_user_id):
            send_telegram_message(ADMIN_CHAT_ID, "⚠️ 세션이 종료된 유저입니다.", thread_id)
            return jsonify({'status': 'ok'})
        
        # 응답 저장소 초기화
        if target_user_id not in admin_responses:
            admin_responses[target_user_id] = []
        
        # 1. 텍스트 메시지 처리
        if 'text' in msg:
            admin_text = msg['text']
            admin_responses[target_user_id].append({
                'type': 'text',
                'content': admin_text
            })
            save_to_google_sheets(target_user_id, 'consultation', admin_text, 'admin')
            update_session_activity(target_user_id)
        
        # 2. 사진 메시지 처리
        elif 'photo' in msg:
            # 가장 큰 해상도의 사진 선택
            photo = msg['photo'][-1]
            file_id = photo['file_id']
            caption = msg.get('caption', '')
            
            # 텔레그램 파일 URL 가져오기
            file_url = get_telegram_file_url(file_id)
            
            if file_url:
                admin_responses[target_user_id].append({
                    'type': 'photo',
                    'url': file_url,
                    'caption': caption
                })
                save_to_google_sheets(target_user_id, 'consultation', f'[사진 전송] {caption}', 'admin')
                update_session_activity(target_user_id)
        
        # 3. 비디오 메시지 처리
        elif 'video' in msg:
            video = msg['video']
            file_id = video['file_id']
            caption = msg.get('caption', '')
            
            file_url = get_telegram_file_url(file_id)
            
            if file_url:
                admin_responses[target_user_id].append({
                    'type': 'video',
                    'url': file_url,
                    'caption': caption
                })
                save_to_google_sheets(target_user_id, 'consultation', f'[비디오 전송] {caption}', 'admin')
                update_session_activity(target_user_id)
        
        # 4. 문서 메시지 처리 (선택사항)
        elif 'document' in msg:
            document = msg['document']
            file_id = document['file_id']
            file_name = document.get('file_name', '파일')
            caption = msg.get('caption', '')
            
            file_url = get_telegram_file_url(file_id)
            
            if file_url:
                admin_responses[target_user_id].append({
                    'type': 'document',
                    'url': file_url,
                    'name': file_name,
                    'caption': caption
                })
                save_to_google_sheets(target_user_id, 'consultation', f'[문서 전송] {file_name}', 'admin')
                update_session_activity(target_user_id)
    
    return jsonify({'status': 'ok'})

@app.route('/api/session_status', methods=['GET'])
def session_status():
    """세션 상태 확인"""
    user_id = session.get('user_id')
    is_active = is_session_active(user_id)
    
    status = {
        'user_id': user_id,
        'session_active': is_active,
        'google_sheets_connected': google_sheets_client is not None
    }
    
    if is_active:
        session_info = active_consultations[user_id]
        status['start_time'] = session_info['start_time'].isoformat()
        status['last_activity'] = session_info['last_activity'].isoformat()
    
    return jsonify(status)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
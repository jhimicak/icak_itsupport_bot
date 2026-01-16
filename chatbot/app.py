from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import requests
import os
from datetime import datetime, timedelta
import uuid
import re
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
CORS(app)

# 환경 변수 설정
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'

# Google Sheets 설정
GOOGLE_SHEET_ID = os.environ.get('GOOGLE_SHEET_ID')

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
SESSION_TIMEOUT_MINUTES = 10  # 세션 타임아웃 (분)

# 저장소
user_sessions = {}
admin_responses = {}
active_consultations = {}
topic_ids = {} # {user_id: message_thread_id}

# Google Sheets 클라이언트 초기화
google_sheets_client = None

def init_google_sheets():
    """Google Sheets API 초기화"""
    global google_sheets_client
    
    try:
        # 환경 변수에서 인증 정보 가져오기
        creds_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
        
        if not creds_json:
            print("⚠️ GOOGLE_SHEETS_CREDENTIALS 환경 변수가 없습니다.")
            return None
        
        # JSON 파싱
        creds_dict = json.loads(creds_json)
        
        # 인증 범위 설정
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # 인증 정보로 클라이언트 생성
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        google_sheets_client = gspread.authorize(credentials)
        
        print("✅ Google Sheets 연결 성공!")
        return google_sheets_client
        
    except Exception as e:
        print(f"❌ Google Sheets 초기화 실패: {e}")
        return None

# 앱 시작 시 Google Sheets 초기화
init_google_sheets()

# --- Google Sheets 저장 함수 ---

def get_or_create_sheet(user_id):
    """사용자별 시트 가져오기 또는 생성"""
    if not google_sheets_client or not GOOGLE_SHEET_ID:
        return None
    
    try:
        spreadsheet = google_sheets_client.open_by_key(GOOGLE_SHEET_ID)
        
        # 시트 이름 (사용자 ID)
        sheet_name = f"User_{user_id}"
        
        try:
            # 기존 시트 가져오기
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            # 시트가 없으면 새로 생성
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
            
            # 헤더 추가
            worksheet.append_row([
                '타임스탬프',
                '날짜',
                '시간',
                '발신자',
                '메시지 타입',
                '메시지 내용',
                '세션 ID'
            ])
            
            # 헤더 서식 설정
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
        print("⚠️ Google Sheets에 저장 실패 (워크시트 없음)")
        return False
    
    try:
        now = kst_now()
        timestamp = now.isoformat()
        date_str = now.strftime('%Y-%m-%d')
        time_str = now.strftime('%H:%M:%S')
        
        # 세션 ID (현재 활성 세션이 있으면 세션 시작 시간 사용)
        session_id = ""
        if user_id in active_consultations:
            session_id = active_consultations[user_id]['start_time'].strftime('%Y%m%d_%H%M%S')
        
        # 발신자 이름 변환
        sender_name = {
            'user': '사용자',
            'bot': '챗봇',
            'admin': '상담원',
            'system': '시스템'
        }.get(sender, sender)
        
        # 행 추가
        worksheet.append_row([
            timestamp,
            date_str,
            time_str,
            sender_name,
            message_type,
            message_content,
            session_id
        ])
        
        print(f"✅ Google Sheets에 저장 완료: {user_id}")
        return True
        
    except Exception as e:
        print(f"❌ Google Sheets 저장 실패: {e}")
        return False

def save_session_summary(user_id, start_time, end_time, reason):
    """상담 세션 요약 저장 (별도 시트)"""
    if not google_sheets_client or not GOOGLE_SHEET_ID:
        return
    
    try:
        spreadsheet = google_sheets_client.open_by_key(GOOGLE_SHEET_ID)
        
        # 세션 요약 시트
        try:
            summary_sheet = spreadsheet.worksheet("SessionSummary")
        except gspread.exceptions.WorksheetNotFound:
            summary_sheet = spreadsheet.add_worksheet(title="SessionSummary", rows=1000, cols=8)
            summary_sheet.append_row([
                '사용자 ID',
                '세션 시작',
                '세션 종료',
                '지속 시간 (초)',
                '종료 사유',
                '날짜',
                '시작 시간',
                '종료 시간'
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
            user_id,
            start_time.isoformat(),
            end_time.isoformat(),
            int(duration),
            reason_text,
            date_str,
            start_time_str,
            end_time_str
        ])
        
        print(f"✅ 세션 요약 저장 완료: {user_id}")
        
    except Exception as e:
        print(f"❌ 세션 요약 저장 실패: {e}")

# --- 상담 세션 관리 함수 ---

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
        
        # 세션 요약 저장
        save_session_summary(user_id, start_time, end_time, reason)
        
        del active_consultations[user_id]
        
        # 관리자에게 알림
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

# --- 텔레그램 헬퍼 함수 ---

def kst_now():
    return datetime.now(timezone.utc) + timedelta(hours=9)

def send_telegram_message(chat_id, text):
    """텔레그램 메시지 발송"""
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")
        return None

# --- notify_admin(새 상담 요청) 수정 ---
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
    
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {
        'chat_id': ADMIN_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'message_thread_id': thread_id
    }
    return requests.post(url, json=data)

def notify_admin_message(user_id, user_message):
    """특정 유저의 Topic 방으로 메시지 전송"""
    thread_id = create_telegram_topic(user_id) # 해당 유저의 방 ID를 가져옴
    
    message = (
        f"👤 <b>유저 메시지</b>\n\n"
        f"{user_message}\n\n"
        f"⏰ {kst_now().strftime('%H:%M:%S')}\n"
        f"ID: [{user_id}]" # 답장을 위해 ID 정보는 하단에 포함
    )
    
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {
        'chat_id': ADMIN_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML',
        'message_thread_id': thread_id # 이 값이 있어야 해당 방으로 배달됨
    }
    return requests.post(url, json=data)

def find_faq_answer(message):
    """FAQ 데이터에서 키워드 매칭"""
    message_lower = message.lower().replace(" ", "")
    for keyword, answer in FAQ_DATA.items():
        if keyword in message_lower:
            return answer
    return None

# --- 텔레그램 주제(Topic) 생성 함수 추가 ---
def create_telegram_topic(user_id):
    """텔레그램 그룹 내에 유저 전용 주제(Topic) 생성"""
    if user_id in topic_ids:
        return topic_ids[user_id]

    url = f'{TELEGRAM_API_URL}/createForumTopic'
    payload = {
        'chat_id': ADMIN_CHAT_ID,
        'name': f"상담: {user_id}"
    }
    
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

# --- 라우트 (API) ---

@app.route('/')
def index():
    """챗봇 웹페이지"""
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())[:8]
    return render_template('chatbot.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """채팅 API 엔드포인트"""
    data = request.json
    user_message = data.get('message', '').strip()
    user_id = session.get('user_id', 'unknown')

    if not user_message:
        return jsonify({'error': '메시지를 입력해주세요'}), 400

    # 사용자 메시지 저장
    save_to_google_sheets(user_id, 'user_message', user_message, 'user')

    # 1. 상담 종료 체크
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

    # 2. 활성 상담 세션이 있는 경우 - 모든 메시지를 관리자에게 전달
    if is_session_active(user_id):
        update_session_activity(user_id)
        notify_admin_message(user_id, user_message)
        
        # response_text = '메시지가 상담원에게 전달되었습니다. 답변을 기다려주세요...'
        # save_to_google_sheets(user_id, 'consultation', user_message, 'user')
        
        # return jsonify({
        #     'type': 'consultation_active',
        #     'message': response_text,
        #     'timestamp': kst_now().isoformat()

        # 안내 문구를 보내지 않기 위해 메시지를 빈 값으로 설정하거나 
        # 클라이언트에서 무시할 특정 타입을 보냅니다.
        save_to_google_sheets(user_id, 'consultation', user_message, 'user')
        
        return jsonify({
            'type': 'consultation_active',
            'message': '', # 메시지를 비워서 보냄
            'timestamp': kst_now().isoformat()
        })

    # 3. 상담원 연결 요청
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

    # 4. FAQ 자동 응답
    faq_answer = find_faq_answer(user_message)
    if faq_answer:
        save_to_google_sheets(user_id, 'faq', faq_answer, 'bot')
        return jsonify({
            'type': 'faq',
            'message': faq_answer,
            'timestamp': kst_now().isoformat()
        })

    # 5. 기본 응답
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

@app.route('/api/check_reply', methods=['GET'])
def check_reply():
    """웹 클라이언트에서 주기적으로 호출하여 관리자 답변 확인"""
    user_id = session.get('user_id')
    
    if user_id in admin_responses and admin_responses[user_id]:
        reply = admin_responses[user_id].pop(0)
        
        # 관리자 답변 저장
        save_to_google_sheets(user_id, 'consultation', reply, 'admin')
        
        # 세션 활동 업데이트
        if is_session_active(user_id):
            update_session_activity(user_id)
        
        return jsonify({'has_reply': True, 'message': reply})
    
    return jsonify({'has_reply': False})

# --- webhook 수정 (관리자 답장 처리) ---
@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    data = request.json
    
    # 텔레그램 주제(Topic) 내에서 온 메시지 처리
    if 'message' in data:
        msg = data['message']
        admin_text = msg.get('text')
        thread_id = msg.get('message_thread_id')
        
        # Topic ID를 통해 어떤 user_id인지 역추적
        target_user_id = next((uid for uid, tid in topic_ids.items() if tid == thread_id), None)
        
        if target_user_id and admin_text:
            # 봇 자신이 보낸 메시지는 무시
            if msg.get('from', {}).get('is_bot'):
                return jsonify({'status': 'ok'})

            if is_session_active(target_user_id):
                if target_user_id not in admin_responses:
                    admin_responses[target_user_id] = []
                admin_responses[target_user_id].append(admin_text)
                update_session_activity(target_user_id)
            else:
                send_telegram_message_to_topic(thread_id, f"⚠️ 세션이 종료된 유저입니다.")
    
    return jsonify({'status': 'ok'})

# 주제 전용 메시지 발송 헬퍼
def send_telegram_message_to_topic(thread_id, text):
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {
        'chat_id': ADMIN_CHAT_ID, 
        'text': text, 
        'message_thread_id': thread_id
    }
    requests.post(url, json=data)

@app.route('/api/session_status', methods=['GET'])
def session_status():
    """현재 세션 상태 확인"""
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
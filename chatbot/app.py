from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import requests
import os
from datetime import datetime
import uuid
import re

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
CORS(app)

# 환경 변수 설정
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID')
TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'

# FAQ 데이터 및 설정
FAQ_DATA = {
    '영업시간': '평일 09:00 - 18:00 (주말 및 공휴일 휴무)',
    '위치': '서울시 강남구 테헤란로 123',
    '연락처': '02-1234-5678',
    '이메일': 'contact@example.com',
    '상담': '상담원 연결을 원하시면 "상담원"을 입력해주세요.',
}

ADMIN_KEYWORDS = ['상담원', '관리자', '직원', '사람', '담당자']

# 저장소 (실 운영시 Redis/DB 권장)
user_sessions = {}
admin_responses = {} 

# --- 헬퍼 함수 ---

def send_telegram_message(chat_id, text):
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        print(f"텔레그램 전송 에러: {e}")
        return None

def notify_admin(user_id, user_message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 관리자가 답장하기 편하도록 USER_ID 형식을 유지합니다.
    message = (
        f"🔔 <b>새 상담 요청</b>\n\n"
        f"USER_ID: [{user_id}]\n"
        f"💬 내용: {user_message}\n"
        f"⏰ {timestamp}\n\n"
        f"이 메시지에 <b>'답장'</b> 기능을 사용하여 답변을 입력해주세요."
    )
    return send_telegram_message(ADMIN_CHAT_ID, message)

def find_faq_answer(message):
    """FAQ 데이터에서 키워드 매칭"""
    message_lower = message.lower().replace(" ", "") # 공백 제거 후 비교
    for keyword, answer in FAQ_DATA.items():
        if keyword in message_lower:
            return answer
    return None

# --- 라우트 (API) ---

@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())[:8]
    return render_template('chatbot.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '').strip()
    user_id = session.get('user_id', 'unknown')

    if not user_message:
        return jsonify({'error': '메시지를 입력해주세요'}), 400

    # 1. 관리자 연결 키워드 체크
    if any(k in user_message for k in ADMIN_KEYWORDS):
        notify_admin(user_id, user_message)
        return jsonify({
            'type': 'admin_request',
            'message': '상담원 연결 요청이 접수되었습니다. 잠시만 기다려주시면 담당자가 답변을 드릴 예정입니다.',
            'timestamp': datetime.now().isoformat()
        })

    # 2. FAQ 자동 응답 체크
    faq_answer = find_faq_answer(user_message)
    if faq_answer:
        response_text = faq_answer
        res_type = 'faq'
    else:
        # 3. 기본 응답 (아무것도 해당 안 될 때)
        response_text = (
            "죄송합니다. 정확한 답변을 찾지 못했습니다.\n\n"
            "<b>도움말 키워드:</b>\n"
            "- 영업시간, 위치, 연락처, 이메일\n\n"
            "직원과 대화를 원하시면 <b>'상담원'</b>이라고 입력해주세요."
        )
        res_type = 'default'

    return jsonify({
        'type': res_type,
        'message': response_text,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/check_reply', methods=['GET'])
def check_reply():
    """웹 클라이언트에서 주기적으로 호출(Polling)하여 관리자 답변 확인"""
    user_id = session.get('user_id')
    if user_id in admin_responses and admin_responses[user_id]:
        reply = admin_responses[user_id].pop(0)
        return jsonify({'has_reply': True, 'message': reply})
    return jsonify({'has_reply': False})

@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    """텔레그램 서버로부터 오는 알림 처리"""
    data = request.json
    
    # 관리자가 특정 메시지에 '답장'을 한 경우
    if 'message' in data and 'reply_to_message' in data['message']:
        admin_text = data['message'].get('text')
        original_text = data['message']['reply_to_message'].get('text', '')
        
        # 원본 메시지에서 USER_ID 추출
        match = re.search(r'USER_ID: \[(.*?)\]', original_text)
        if match:
            target_user_id = match.group(1)
            if target_user_id not in admin_responses:
                admin_responses[target_user_id] = []
            admin_responses[target_user_id].append(admin_text)
            
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
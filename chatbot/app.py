from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import requests
import os
from datetime import datetime
import uuid
import re

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'
CORS(app)

# 직접 입력 대신 환경 변수에서 가져오도록 수정
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
ADMIN_CHAT_ID = int(os.environ.get('ADMIN_CHAT_ID'))
TELEGRAM_API_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}'

# 대화 데이터 및 관리자 답변 임시 저장소
# 실제 운영시에는 Redis나 DB 사용 권장
user_sessions = {}
admin_responses = {} # 사용자 ID별로 관리자의 미확인 답변 저장

def send_telegram_message(chat_id, text):
    url = f'{TELEGRAM_API_URL}/sendMessage'
    data = {'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}
    return requests.post(url, json=data).json()

def notify_admin(user_id, user_message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 답장 시 ID 파싱을 위해 형식을 유지하세요.
    message = f"🔔 <b>새 상담 요청</b>\n\nUSER_ID: [{user_id}]\n💬 내용: {user_message}\n⏰ {timestamp}\n\n이 메시지에 '답장'하면 사용자에게 전달됩니다."
    return send_telegram_message(ADMIN_CHAT_ID, message)

@app.route('/')
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())[:8] # 식별하기 쉽게 짧게 자름
    return render_template('chatbot.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.json
    user_message = data.get('message', '').strip()
    user_id = session.get('user_id', 'unknown')
    
    # 1. 관리자 호출 키워드 체크
    admin_keywords = ['상담원', '관리자', '직원', '사람']
    if any(k in user_message for k in admin_keywords):
        notify_admin(user_id, user_message)
        return jsonify({'type': 'admin_request', 'message': '상담원 연결 요청이 전달되었습니다. 잠시만 기다려주세요.'})

    # 2. FAQ 처리 등 기존 로직...
    return jsonify({'type': 'default', 'message': '상담원에게 메시지를 보냈습니다. 답변을 기다려주세요.'})

@app.route('/api/check_reply', methods=['GET'])
def check_reply():
    """웹 브라우저가 주기적으로 호출하여 관리자의 답변이 있는지 확인"""
    user_id = session.get('user_id')
    if user_id in admin_responses and admin_responses[user_id]:
        reply = admin_responses[user_id].pop(0) # 가장 오래된 답변부터 꺼냄
        return jsonify({'has_reply': True, 'message': reply})
    return jsonify({'has_reply': False})

@app.route('/api/webhook', methods=['POST'])
def telegram_webhook():
    """텔레그램에서 보낸 메시지 처리"""
    data = request.json
    
    # 관리자가 답장(Reply)을 한 경우만 처리
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
    # Render가 주는 PORT 환경변수를 읽고, 없으면 5000을 사용
    port = int(os.environ.get("PORT", 5000))
    # 0.0.0.0으로 설정해야 외부(Render의 로드밸런서)에서 접속 가능합니다.
    app.run(host='0.0.0.0', port=port)
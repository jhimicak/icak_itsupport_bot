"""
Groq API 클라이언트
- TF-IDF 검색 결과를 Groq LLM으로 정제
- 자연스러운 한국어 답변 생성
"""

import os
from groq import Groq
from typing import List, Dict, Optional


class GroqClient:
    """Groq API 클라이언트 클래스"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Groq API 키 (없으면 환경 변수에서 가져옴)
        """
        self.api_key = api_key or os.environ.get('GROQ_API_KEY')
        
        if not self.api_key:
            print("⚠️ GROQ_API_KEY가 설정되지 않았습니다. LLM 정제 기능이 비활성화됩니다.")
            self.client = None
        else:
            try:
                self.client = Groq(api_key=self.api_key)
                print("✅ Groq API 클라이언트 초기화 완료")
            except Exception as e:
                print(f"❌ Groq API 초기화 실패: {e}")
                self.client = None
    
    def is_available(self) -> bool:
        """Groq API 사용 가능 여부 확인"""
        return self.client is not None
    
    def refine_answer(
        self, 
        query: str, 
        search_results: List[Dict], 
        model: str = "llama-3.1-8b-instant"
    ) -> Optional[str]:
        """
        검색 결과를 기반으로 정제된 답변 생성
        
        Args:
            query: 사용자 질문
            search_results: TF-IDF 검색 결과 리스트
            model: 사용할 Groq 모델
            
        Returns:
            정제된 답변 (실패 시 None)
        """
        if not self.is_available():
            return None
        
        if not search_results:
            return None
        
        # 검색 결과를 컨텍스트로 변환
        context_parts = []
        for i, result in enumerate(search_results[:20], 1):  # 상위 20개 사용
            chunk = result['chunk']
            text = chunk['text']
            page = chunk['metadata'].get('page_number', '?')
            context_parts.append(f"[문서 {i} - 페이지 {page}]\n{text}")
        
        context = "\n\n".join(context_parts)
        
        # 프롬프트 구성
        system_prompt = """당신은 해외건설협회 교육훈련팀의 교육 안내 전문가입니다.
모든 답변은 제공된 문서에 기반해서 정확하게 답변해주세요.

🎯 핵심 원칙:
1. **완전성 보장**: 검색 결과에 있는 모든 관련 항목을 빠짐없이 포함하세요
2. **단계별 사고**: 답변 전에 먼저 관련 항목이 총 몇 개인지 확인하세요
3. **형식 준수**: 목록 먼저 제시 → 상세 설명은 그 다음

📋 답변 형식:
- 특정 월 교육 질문 시:
  Step 1) 해당 월 교육 개수 확인
  Step 2) 모든 교육을 "번호. 교육명 (날짜)" 형식으로 나열
  Step 3) 필요시 주요 교육에 대한 상세 설명 추가

✅ 답변 규칙:
1. 문서 내용만 기반으로 답변 (추측 금지)
2. **여러 항목이 있으면 반드시 모두 나열** (일부만 선택 금지)
3. 날짜, 시간, 연락처, 비용 등 구체적 정보 정확히 포함
4. 데이터에 없는 내용은 "02-3406-1111로 문의 바랍니다"
5. 간결하되 중요 정보는 누락하지 않음

📌 시나리오별 가이드:

**"3월 교육" 같은 월별 질문:**
→ 해당 월의 모든 교육을 번호 매겨 나열
예: "3월에는 총 11개 교육이 진행됩니다:
1. 건설계약 실무 (3월 4일)
2. 프로젝트 관리 (3월 7일)
..."

**교육 일정 질문:**
→ 해당 과정의 모든 회차 날짜 제시
예: "이 과정은 3월 4일, 7월 14일 두 차례 진행됩니다"

**교육비 질문:**
→ 중소/중견기업 무료 먼저 언급
예: "중소·중견기업 재직자는 무료이며, 대기업은 XX원입니다"

**"ChatGPT 교육" 같은 키워드 질문:**
→ 관련된 모든 과정 나열
예: "ChatGPT 관련 교육은 2개입니다: 1. ChatGPT Basic, 2. ChatGPT Advanced"

**협약서/취소/수료 등 절차 질문:**
→ 방법과 기한 명확히 안내

⚠️ 중요: 검색 결과에 여러 항목이 있다면 **절대 일부만 선택하지 말고 모두 포함**하세요."""

        user_prompt = f"""질문: {query}

참고 문서:
{context}

위 문서를 참고하여 질문에 답변해주세요."""

        try:
            # Groq API 호출
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model=model,
                temperature=0.2,  # 더 일관성 있는 답변 (0.3 → 0.2)
                max_tokens=1000,   # 답변 길이 증가 (500 → 1000)
            )
            
            answer = chat_completion.choices[0].message.content
            return answer.strip()
            
        except Exception as e:
            print(f"❌ Groq API 호출 실패: {e}")
            return None
    
    def generate_answer_with_sources(
        self,
        query: str,
        search_results: List[Dict]
    ) -> Dict:
        """
        검색 결과를 정제하고 출처 정보와 함께 반환
        
        Args:
            query: 사용자 질문
            search_results: TF-IDF 검색 결과
            
        Returns:
            {
                'answer': 정제된 답변,
                'sources': 출처 정보,
                'refined': Groq 사용 여부
            }
        """
        # Groq로 답변 정제 시도
        refined_answer = self.refine_answer(query, search_results)
        
        # 출처 정보 추출
        sources = []
        for result in search_results[:3]:
            chunk = result['chunk']
            sources.append({
                'page': chunk['metadata'].get('page_number', '?'),
                'similarity': result.get('similarity', 0)
            })
        
        if refined_answer:
            return {
                'answer': refined_answer,
                'sources': sources,
                'refined': True,
                'confidence': 'high'
            }
        else:
            # Groq 실패 시 원본 반환
            original_answer = "\n\n".join([
                result['chunk']['text'] 
                for result in search_results[:2]
            ])
            return {
                'answer': original_answer,
                'sources': sources,
                'refined': False,
                'confidence': 'medium'
            }


def test_groq_client():
    """테스트 함수"""
    client = GroqClient()
    
    if not client.is_available():
        print("Groq API 키가 설정되지 않았습니다.")
        return
    
    # 테스트 검색 결과
    test_results = [
        {
            'chunk': {
                'text': '비밀번호 재설정 방법:\n1. 로그인 페이지에서 "비밀번호 찾기" 클릭\n2. 등록된 이메일 주소 입력\n3. 이메일로 받은 인증 코드 입력\n4. 새 비밀번호 설정',
                'metadata': {'page_number': 5}
            },
            'similarity': 0.85
        }
    ]
    
    result = client.generate_answer_with_sources(
        "비밀번호를 어떻게 재설정하나요?",
        test_results
    )
    
    print(f"\n답변: {result['answer']}")
    print(f"정제됨: {result['refined']}")
    print(f"출처: 페이지 {result['sources'][0]['page']}")


if __name__ == "__main__":
    test_groq_client()

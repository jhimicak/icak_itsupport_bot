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
        model: str = "llama-3.3-70b-versatile"
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
        for i, result in enumerate(search_results[:3], 1):  # 상위 3개만 사용
            chunk = result['chunk']
            text = chunk['text']
            page = chunk['metadata'].get('page_number', '?')
            context_parts.append(f"[문서 {i} - 페이지 {page}]\n{text}")
        
        context = "\n\n".join(context_parts)
        
        # 프롬프트 구성
        system_prompt = """당신은 IT 지원 전문 상담원입니다. 
사용자의 질문에 대해 제공된 문서를 참고하여 정확하고 친절하게 답변해주세요.

답변 규칙:
1. 문서 내용을 기반으로만 답변하세요
2. 간결하고 명확하게 작성하세요
3. 단계가 있다면 번호를 매겨 설명하세요
4. 문서에 없는 내용은 "문서에서 해당 정보를 찾을 수 없습니다"라고 답변하세요
5. 한국어로 답변하세요"""

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
                temperature=0.3,  # 일관성 있는 답변을 위해 낮게 설정
                max_tokens=500,   # 답변 길이 제한
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

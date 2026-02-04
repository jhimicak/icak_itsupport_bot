"""
경량 RAG 시스템 (TF-IDF 기반)
- 메모리 효율적 (~10-50MB)
- sentence-transformers 대신 TF-IDF 사용
- 512MB 제한 환경에서 안정적으로 작동
"""

import os
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Tuple
from pdf_processor import PDFProcessor


class RAGSystemLite:
    """경량 RAG 시스템 클래스 (TF-IDF 기반)"""
    
    def __init__(self):
        """
        TF-IDF 벡터라이저 초기화
        """
        print("🔄 경량 RAG 시스템 초기화 중 (TF-IDF)...")
        
        # TF-IDF 벡터라이저 (한국어 지원)
        self.vectorizer = TfidfVectorizer(
            max_features=5000,  # 최대 특성 수 제한 (메모리 절약)
            ngram_range=(1, 2),  # 1-gram, 2-gram 사용
            min_df=1,
            max_df=0.95,
            sublinear_tf=True  # 로그 스케일링
        )
        
        self.chunks = []
        self.tfidf_matrix = None
        
        print("✅ 경량 RAG 시스템 초기화 완료")
    
    def build_index(self, chunks: List[Dict[str, any]]):
        """
        청크 리스트로부터 TF-IDF 인덱스 생성
        
        Args:
            chunks: PDF 청크 리스트
        """
        if not chunks:
            print("⚠️ 청크가 비어있습니다.")
            return
        
        print(f"🔄 {len(chunks)}개 청크 인덱싱 중 (TF-IDF)...")
        
        # 청크 저장
        self.chunks = chunks
        
        # 텍스트 추출
        texts = [chunk['text'] for chunk in chunks]
        
        # TF-IDF 행렬 생성
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)
        
        print(f"✅ 인덱스 생성 완료: {len(chunks)}개 문서, {self.tfidf_matrix.shape[1]}개 특성")
    
    def search(self, query: str, top_k: int = 3) -> List[Tuple[Dict, float]]:
        """
        질문과 가장 유사한 청크 검색
        
        Args:
            query: 사용자 질문
            top_k: 반환할 상위 결과 개수
            
        Returns:
            (청크, 유사도) 튜플 리스트
        """
        if self.tfidf_matrix is None or len(self.chunks) == 0:
            print("⚠️ 인덱스가 비어있습니다.")
            return []
        
        # 질문 벡터화
        query_vector = self.vectorizer.transform([query])
        
        # 코사인 유사도 계산
        similarities = cosine_similarity(query_vector, self.tfidf_matrix).flatten()
        
        # 상위 k개 인덱스 추출
        top_indices = similarities.argsort()[-top_k:][::-1]
        
        # 결과 정리
        results = []
        for idx in top_indices:
            if idx < len(self.chunks):
                similarity = float(similarities[idx])
                results.append((self.chunks[idx], similarity))
        
        return results
    
    def generate_answer(self, query: str, top_k: int = 3, similarity_threshold: float = 0.1) -> Dict:
        """
        질문에 대한 답변 생성
        
        Args:
            query: 사용자 질문
            top_k: 검색할 상위 결과 개수
            similarity_threshold: 유사도 임계값 (0~1, 높을수록 유사)
            
        Returns:
            답변 딕셔너리
        """
        # 유사 청크 검색
        results = self.search(query, top_k)
        
        if not results:
            return {
                'answer': None,
                'sources': [],
                'confidence': 'none'
            }
        
        # 가장 유사한 결과 확인
        best_chunk, best_similarity = results[0]
        
        # 임계값 체크
        if best_similarity < similarity_threshold:
            return {
                'answer': None,
                'sources': [],
                'confidence': 'low',
                'similarity': best_similarity
            }
        
        # 답변 생성 (상위 결과 조합)
        answer_parts = []
        sources = []
        
        for chunk, similarity in results[:2]:  # 상위 2개만 사용
            if similarity >= similarity_threshold:
                answer_parts.append(chunk['text'])
                sources.append({
                    'page': chunk['metadata'].get('page_number', '?'),
                    'source': chunk['metadata'].get('source', ''),
                    'similarity': similarity
                })
        
        if not answer_parts:
            return {
                'answer': None,
                'sources': [],
                'confidence': 'low'
            }
        
        # 답변 포맷팅
        answer = "\n\n".join(answer_parts)
        
        # 신뢰도 계산
        confidence = 'high' if best_similarity > 0.3 else 'medium'
        
        return {
            'answer': answer,
            'sources': sources,
            'confidence': confidence,
            'similarity': best_similarity
        }
    
    def save_index(self, index_dir: str):
        """
        인덱스와 청크를 파일로 저장
        
        Args:
            index_dir: 저장 디렉토리
        """
        os.makedirs(index_dir, exist_ok=True)
        
        # TF-IDF 벡터라이저 저장
        vectorizer_path = os.path.join(index_dir, 'vectorizer.pkl')
        with open(vectorizer_path, 'wb') as f:
            pickle.dump(self.vectorizer, f)
        
        # TF-IDF 행렬 저장
        matrix_path = os.path.join(index_dir, 'tfidf_matrix.pkl')
        with open(matrix_path, 'wb') as f:
            pickle.dump(self.tfidf_matrix, f)
        
        # 청크 저장
        chunks_path = os.path.join(index_dir, 'chunks.pkl')
        with open(chunks_path, 'wb') as f:
            pickle.dump(self.chunks, f)
        
        print(f"✅ 인덱스 저장 완료: {index_dir}")
    
    def load_index(self, index_dir: str) -> bool:
        """
        저장된 인덱스와 청크 로드
        
        Args:
            index_dir: 저장 디렉토리
            
        Returns:
            성공 여부
        """
        try:
            # TF-IDF 벡터라이저 로드
            vectorizer_path = os.path.join(index_dir, 'vectorizer.pkl')
            with open(vectorizer_path, 'rb') as f:
                self.vectorizer = pickle.load(f)
            
            # TF-IDF 행렬 로드
            matrix_path = os.path.join(index_dir, 'tfidf_matrix.pkl')
            with open(matrix_path, 'rb') as f:
                self.tfidf_matrix = pickle.load(f)
            
            # 청크 로드
            chunks_path = os.path.join(index_dir, 'chunks.pkl')
            with open(chunks_path, 'rb') as f:
                self.chunks = pickle.load(f)
            
            print(f"✅ 인덱스 로드 완료: {len(self.chunks)}개 문서")
            return True
            
        except Exception as e:
            print(f"❌ 인덱스 로드 실패: {e}")
            return False


def test_rag_system():
    """테스트 함수"""
    # PDF 처리
    processor = PDFProcessor()
    chunks = processor.process_pdf("test.pdf")
    
    # RAG 시스템 초기화
    rag = RAGSystemLite()
    rag.build_index(chunks)
    
    # 테스트 질문
    test_queries = [
        "비밀번호를 재설정하는 방법은?",
        "영업시간이 어떻게 되나요?",
        "연락처를 알려주세요"
    ]
    
    for query in test_queries:
        print(f"\n질문: {query}")
        result = rag.generate_answer(query)
        
        if result['answer']:
            print(f"답변: {result['answer'][:200]}...")
            print(f"신뢰도: {result['confidence']}")
            print(f"유사도: {result['similarity']:.3f}")
            print(f"출처: 페이지 {result['sources'][0]['page']}")
        else:
            print("답변을 찾을 수 없습니다.")


if __name__ == "__main__":
    test_rag_system()

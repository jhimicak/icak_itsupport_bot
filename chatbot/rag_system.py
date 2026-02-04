"""
RAG (Retrieval-Augmented Generation) 시스템
- 임베딩 생성 (sentence-transformers)
- 벡터 검색 (FAISS)
- 답변 생성
"""

import os
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
from typing import List, Dict, Tuple
from pdf_processor import PDFProcessor


class RAGSystem:
    """RAG 시스템 클래스"""
    
    def __init__(self, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        """
        Args:
            model_name: sentence-transformers 모델 이름 (한국어 지원)
        """
        print(f"🔄 임베딩 모델 로딩 중: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        
        # FAISS 인덱스
        self.index = None
        self.chunks = []
        
        print(f"✅ RAG 시스템 초기화 완료 (차원: {self.dimension})")
    
    def create_embeddings(self, texts: List[str]) -> np.ndarray:
        """
        텍스트 리스트를 임베딩으로 변환
        
        Args:
            texts: 텍스트 리스트
            
        Returns:
            임베딩 배열 (n_texts, dimension)
        """
        embeddings = self.model.encode(texts, show_progress_bar=True)
        return np.array(embeddings).astype('float32')
    
    def build_index(self, chunks: List[Dict[str, any]]):
        """
        청크 리스트로부터 FAISS 인덱스 생성
        
        Args:
            chunks: PDF 청크 리스트
        """
        if not chunks:
            print("⚠️ 청크가 비어있습니다.")
            return
        
        print(f"🔄 {len(chunks)}개 청크 인덱싱 중...")
        
        # 청크 저장
        self.chunks = chunks
        
        # 텍스트 추출
        texts = [chunk['text'] for chunk in chunks]
        
        # 임베딩 생성
        embeddings = self.create_embeddings(texts)
        
        # FAISS 인덱스 생성 (L2 거리 기반)
        self.index = faiss.IndexFlatL2(self.dimension)
        self.index.add(embeddings)
        
        print(f"✅ 인덱스 생성 완료: {self.index.ntotal}개 벡터")
    
    def search(self, query: str, top_k: int = 3) -> List[Tuple[Dict, float]]:
        """
        질문과 가장 유사한 청크 검색
        
        Args:
            query: 사용자 질문
            top_k: 반환할 상위 결과 개수
            
        Returns:
            (청크, 거리) 튜플 리스트
        """
        if self.index is None or self.index.ntotal == 0:
            print("⚠️ 인덱스가 비어있습니다.")
            return []
        
        # 질문 임베딩
        query_embedding = self.create_embeddings([query])
        
        # 검색
        distances, indices = self.index.search(query_embedding, min(top_k, self.index.ntotal))
        
        # 결과 정리
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < len(self.chunks):
                results.append((self.chunks[idx], float(dist)))
        
        return results
    
    def generate_answer(self, query: str, top_k: int = 3, distance_threshold: float = 1.5) -> Dict:
        """
        질문에 대한 답변 생성
        
        Args:
            query: 사용자 질문
            top_k: 검색할 상위 결과 개수
            distance_threshold: 유사도 임계값 (낮을수록 유사)
            
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
        best_chunk, best_distance = results[0]
        
        # 임계값 체크
        if best_distance > distance_threshold:
            return {
                'answer': None,
                'sources': [],
                'confidence': 'low',
                'distance': best_distance
            }
        
        # 답변 생성 (상위 결과 조합)
        answer_parts = []
        sources = []
        
        for chunk, distance in results[:2]:  # 상위 2개만 사용
            if distance <= distance_threshold:
                answer_parts.append(chunk['text'])
                sources.append({
                    'page': chunk['metadata'].get('page_number', '?'),
                    'source': chunk['metadata'].get('source', ''),
                    'distance': distance
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
        confidence = 'high' if best_distance < 0.8 else 'medium'
        
        return {
            'answer': answer,
            'sources': sources,
            'confidence': confidence,
            'distance': best_distance
        }
    
    def save_index(self, index_dir: str):
        """
        인덱스와 청크를 파일로 저장
        
        Args:
            index_dir: 저장 디렉토리
        """
        os.makedirs(index_dir, exist_ok=True)
        
        # FAISS 인덱스 저장
        index_path = os.path.join(index_dir, 'faiss.index')
        faiss.write_index(self.index, index_path)
        
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
            # FAISS 인덱스 로드
            index_path = os.path.join(index_dir, 'faiss.index')
            self.index = faiss.read_index(index_path)
            
            # 청크 로드
            chunks_path = os.path.join(index_dir, 'chunks.pkl')
            with open(chunks_path, 'rb') as f:
                self.chunks = pickle.load(f)
            
            print(f"✅ 인덱스 로드 완료: {self.index.ntotal}개 벡터")
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
    rag = RAGSystem()
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
            print(f"출처: 페이지 {result['sources'][0]['page']}")
        else:
            print("답변을 찾을 수 없습니다.")


if __name__ == "__main__":
    test_rag_system()

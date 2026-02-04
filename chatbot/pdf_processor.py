"""
PDF 문서 처리 모듈
- PDF에서 텍스트 추출
- 텍스트를 의미 있는 청크로 분할
"""

import pdfplumber
import re
from typing import List, Dict


class PDFProcessor:
    """PDF 문서 처리 클래스"""
    
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        """
        Args:
            chunk_size: 청크당 최대 문자 수
            chunk_overlap: 청크 간 겹치는 문자 수
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def extract_text_from_pdf(self, pdf_path: str) -> List[Dict[str, any]]:
        """
        PDF 파일에서 텍스트 추출
        
        Args:
            pdf_path: PDF 파일 경로
            
        Returns:
            페이지별 텍스트와 메타데이터 리스트
        """
        pages_data = []
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    
                    if text and text.strip():
                        pages_data.append({
                            'page_number': page_num,
                            'text': text.strip(),
                            'source': pdf_path
                        })
            
            print(f"✅ PDF 추출 완료: {len(pages_data)} 페이지")
            return pages_data
            
        except Exception as e:
            print(f"❌ PDF 추출 실패: {e}")
            return []
    
    def split_text_into_chunks(self, text: str, metadata: Dict = None) -> List[Dict[str, any]]:
        """
        텍스트를 청크로 분할
        
        Args:
            text: 분할할 텍스트
            metadata: 메타데이터 (페이지 번호 등)
            
        Returns:
            청크 리스트
        """
        # 문단 단위로 먼저 분할
        paragraphs = re.split(r'\n\s*\n', text)
        
        chunks = []
        current_chunk = ""
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # 현재 청크에 추가했을 때 크기 확인
            if len(current_chunk) + len(para) + 2 <= self.chunk_size:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para
            else:
                # 현재 청크 저장
                if current_chunk:
                    chunk_data = {
                        'text': current_chunk,
                        'metadata': metadata or {}
                    }
                    chunks.append(chunk_data)
                
                # 새 청크 시작
                current_chunk = para
        
        # 마지막 청크 저장
        if current_chunk:
            chunk_data = {
                'text': current_chunk,
                'metadata': metadata or {}
            }
            chunks.append(chunk_data)
        
        return chunks
    
    def process_pdf(self, pdf_path: str) -> List[Dict[str, any]]:
        """
        PDF 전체 처리: 텍스트 추출 + 청크 분할
        
        Args:
            pdf_path: PDF 파일 경로
            
        Returns:
            모든 청크 리스트
        """
        all_chunks = []
        
        # 페이지별 텍스트 추출
        pages_data = self.extract_text_from_pdf(pdf_path)
        
        # 각 페이지를 청크로 분할
        for page_data in pages_data:
            metadata = {
                'page_number': page_data['page_number'],
                'source': page_data['source']
            }
            
            chunks = self.split_text_into_chunks(page_data['text'], metadata)
            all_chunks.extend(chunks)
        
        print(f"✅ 총 {len(all_chunks)}개 청크 생성")
        return all_chunks


def test_pdf_processor():
    """테스트 함수"""
    processor = PDFProcessor(chunk_size=500, chunk_overlap=50)
    
    # 테스트 PDF 경로 (실제 파일로 교체 필요)
    test_pdf = "test.pdf"
    
    chunks = processor.process_pdf(test_pdf)
    
    print(f"\n총 청크 수: {len(chunks)}")
    if chunks:
        print(f"\n첫 번째 청크 예시:")
        print(f"페이지: {chunks[0]['metadata']['page_number']}")
        print(f"텍스트: {chunks[0]['text'][:200]}...")


if __name__ == "__main__":
    test_pdf_processor()

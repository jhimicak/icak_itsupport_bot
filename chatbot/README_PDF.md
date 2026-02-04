# PDF 기반 RAG 챗봇 - 관리자 가이드

## 📄 PDF 문서 준비 방법

### 1. PDF 파일 배치

PDF 파일을 다음 폴더에 넣어주세요:

```
chatbot/pdf_documents/
```

**예시:**
```
chatbot/
├── app.py
├── pdf_processor.py
├── rag_system.py
└── pdf_documents/
    ├── IT지원매뉴얼.pdf
    ├── FAQ문서.pdf
    └── 사용자가이드.pdf
```

### 2. 서버 시작

```bash
cd chatbot
python app.py
```

서버가 시작되면 자동으로:
1. `pdf_documents/` 폴더의 모든 PDF 파일을 검색
2. 텍스트 추출 및 청크 분할
3. 임베딩 생성 및 FAISS 인덱스 빌드
4. `pdf_documents/index/` 폴더에 인덱스 저장

### 3. 콘솔 출력 확인

```
🔄 RAG 시스템 초기화 중...
📄 3개 PDF 파일 발견, 인덱싱 시작...
  처리 중: IT지원매뉴얼.pdf
✅ PDF 추출 완료: 25 페이지
✅ 총 120개 청크 생성
  처리 중: FAQ문서.pdf
✅ PDF 추출 완료: 10 페이지
✅ 총 45개 청크 생성
📊 총 165개 청크 생성, 인덱스 빌드 중...
✅ PDF 인덱싱 완료!
```

---

## 🔄 PDF 업데이트 방법

### 새 PDF 추가 또는 기존 PDF 수정:

1. `pdf_documents/` 폴더에 PDF 추가/수정
2. 기존 인덱스 삭제:
   ```bash
   rm -rf chatbot/pdf_documents/index/
   # Windows: rmdir /s chatbot\pdf_documents\index
   ```
3. 서버 재시작:
   ```bash
   python app.py
   ```

서버가 자동으로 모든 PDF를 재인덱싱합니다.

---

## ⚙️ 설정 조정

### 청크 크기 조정 (`app.py`):

```python
pdf_processor = PDFProcessor(
    chunk_size=500,      # 청크당 문자 수 (기본값: 500)
    chunk_overlap=50     # 청크 간 겹침 (기본값: 50)
)
```

### 답변 임계값 조정 (`app.py`):

```python
result = rag_system.generate_answer(
    user_message, 
    top_k=3,                    # 검색할 상위 결과 개수
    distance_threshold=1.5      # 유사도 임계값 (낮을수록 엄격)
)
```

---

## 📊 인덱스 관리

### 인덱스 파일 위치:
```
chatbot/pdf_documents/index/
├── faiss.index      # FAISS 벡터 인덱스
└── chunks.pkl       # 청크 데이터 (텍스트 + 메타데이터)
```

### 인덱스 재생성이 필요한 경우:
- PDF 파일 추가/수정/삭제
- 청크 크기 변경
- 임베딩 모델 변경

---

## 🐛 문제 해결

### "PDF 파일이 없습니다" 메시지:
- `pdf_documents/` 폴더에 PDF 파일이 있는지 확인
- 파일 확장자가 `.pdf`인지 확인

### "PDF에서 텍스트를 추출할 수 없습니다":
- 스캔 이미지 PDF인 경우 OCR 필요
- 텍스트 기반 PDF로 변환 후 재시도

### 인덱스 로드 실패:
- `pdf_documents/index/` 폴더 삭제 후 서버 재시작
- 자동으로 재인덱싱됩니다

---

## 💡 권장 사항

### PDF 문서 준비:
- **텍스트 기반 PDF** 사용 (스캔 이미지 PDF 피하기)
- **명확한 구조**: 제목, 섹션, 문단 구분
- **적절한 크기**: 페이지당 500-1000자 권장

### 성능 최적화:
- PDF 파일 수: 10개 이하 권장
- 총 페이지 수: 200페이지 이하 권장
- 파일 크기: 각 10MB 이하 권장

---

## 📝 사용자 경험

사용자는 PDF 업로드 없이 바로 질문할 수 있습니다:

```
사용자: "비밀번호 재설정 방법은?"
챗봇: [PDF에서 관련 내용 검색하여 답변]
      📄 출처: 페이지 12
```

관리자가 미리 준비한 PDF 문서를 기반으로 자동 답변합니다.

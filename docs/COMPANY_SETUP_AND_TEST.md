# 사내 환경 설정 및 테스트 가이드

이 문서는 사내 RAGFlow와 사내 Open WebUI 환경에서 이 wrapper를 실제로 띄우고 검증하는 절차를 정리합니다.

대상 환경:

- RAGFlow: 사내망 HTTP/HTTPS 엔드포인트
- Open WebUI: 사내 WSL 또는 Docker 환경
- Wrapper: Linux/WSL에서 FastAPI + Uvicorn 실행

핵심 원칙:

- 모델은 wrapper만 호출합니다.
- RAGFlow API key는 wrapper 서버 환경변수에만 둡니다.
- Open WebUI에는 RAGFlow URL이나 API key를 직접 넣지 않습니다.
- `dataset_id`는 사용하지 않고 `dataset_name`/alias만 사용합니다.

## 1. 저장소 가져오기

```bash
git clone https://github.com/Julirsia/rfow.git
cd rfow
```

이미 사내 Git 미러를 쓸 예정이면 해당 URL로 clone 해도 됩니다.

## 2. Python 환경 준비

권장 버전:

- Python 3.11 이상

설치:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 3. dataset 설정

예제 파일 복사:

```bash
cp config/datasets.example.yaml config/datasets.yaml
```

`config/datasets.yaml` 예시:

```yaml
datasets:
  - name: hr_handbook
    display_name: HR Handbook
    ragflow_name: HR Handbook
    vendor: apple
    doc_type: feature
    description: Apple 장비의 기능 설명, 사용법, 운영 가이드 문서
    aliases: ["hr", "handbook", "인사규정"]
    enabled: true

  - name: finance_policy
    display_name: Finance Policy
    ragflow_name: Finance Policy
    vendor: banana
    doc_type: spec
    description: Banana 장비의 기술 사양, 수치 기준, 포트, 성능 문서
    aliases: ["finance", "expense", "출장비"]
    enabled: true
```

규칙:

- `name`: Open WebUI 모델이 사용할 canonical public name
- `display_name`: 사람이 읽기 좋은 이름
- `ragflow_name`: 실제 RAGFlow dataset 이름
- `vendor`: 제조사, 제품군, 사업영역 같은 큰 분류
- `doc_type`: `spec`, `feature`, `misc` 같은 문서 종류
- `description`: 어떤 질문에 적합한 dataset인지 보여주는 짧은 설명
- `aliases`: 모델 입력 오타/별칭 흡수용
- `name`, `display_name`, `aliases`, `ragflow_name`이 서로 충돌하지 않게 유지
- `description`은 짧고 직접적으로 쓰는 편이 좋음. 예: `Apple 장비의 하드웨어 사양 문서`

## 4. 환경변수 설정

```bash
cp .env.example .env
```

`.env`에서 최소한 아래를 수정합니다.

```dotenv
RAGFLOW_BASE_URL=https://ragflow.company.internal
RAGFLOW_API_KEY=ragflow_api_xxx
DATASET_CONFIG_PATH=config/datasets.yaml
PUBLIC_BASE_URL=http://localhost:8090
REQUEST_TIMEOUT_SECONDS=20
DATASET_CACHE_TTL_SECONDS=60
DEFAULT_TOP_K=4
MAX_TOP_K=8
SNIPPET_MAX_CHARS=320
CONTEXT_MAX_CHARS=1500
DOWNLOAD_TOKEN_TTL_SECONDS=900
DOWNLOAD_TOKEN_SECRET=replace-with-random-secret
SOURCE_REF_TTL_SECONDS=86400
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
LOG_LEVEL=INFO
```

주의:

- `PUBLIC_BASE_URL`은 Open WebUI 또는 브라우저에서 실제로 접근 가능한 wrapper 주소여야 합니다.
- `DOWNLOAD_TOKEN_SECRET`는 랜덤 문자열을 사용합니다.
- `RAGFLOW_BASE_URL`은 UI 주소가 아니라 API가 붙는 실제 RAGFlow base URL이어야 합니다.

## 5. Wrapper 실행

```bash
. .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8090
```

확인:

- `http://localhost:8090/docs`
- `http://localhost:8090/redoc`
- `http://localhost:8090/openapi.json`

## 6. 1차 Smoke Test

### 6-1. Health

```bash
curl -sS http://127.0.0.1:8090/health | jq
```

기대:

- `ok: true`
- `ragflow_status: ok` 또는 최소 `degraded`

### 6-2. Dataset 목록

```bash
curl -sS http://127.0.0.1:8090/datasets | jq
```

기대:

- allowlist에 넣은 dataset만 보임
- `vendor`, `doc_type`, `description`이 함께 보임
- `status: ready`

### 6-3. 문서 목록

```bash
curl -sS http://127.0.0.1:8090/datasets/hr_handbook/documents | jq
```

기대:

- `document_name`
- `source_ref`
- `source_download_url`

### 6-4. 단일 dataset 검색

```bash
curl -sS -X POST http://127.0.0.1:8090/search_dataset \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "연차는 언제 소멸돼?",
    "dataset_name": "hr_handbook",
    "top_k": 4
  }' | jq
```

기대:

- `found: true`
- `chunks`에 `dataset_name`, `document_name`, `snippet`, `score`, `source_ref`, `source_download_url`
- `sources`에 dedupe된 다운로드 링크

### 6-4-1. 같은 문서 안에서 추가 검색

먼저 `search_dataset` 또는 `search_all` 응답에서 `sources[0].source_ref` 값을 복사합니다.

```bash
curl -sS -X POST http://127.0.0.1:8090/search_source \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "이 문서 안에서 연차 사용 기한만 더 자세히 찾아줘",
    "source_ref": "<search 결과의 source_ref>",
    "top_k": 4
  }' | jq
```

기대:

- `selected_dataset`
- `selected_document`
- `chunks`와 `sources`가 모두 동일 문서만 가리킴
- follow-up search가 `file_id`가 아니라 wrapper가 준 `source_ref`로만 동작

### 6-5. 전체 검색

```bash
curl -sS -X POST http://127.0.0.1:8090/search_all \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "출장비 정산 기준이 뭐야?",
    "top_k": 4
  }' | jq
```

기대:

- dataset이 여러 개일 때 `matched_datasets`가 채워짐

### 6-6. 다운로드 링크 실제 확인

1. `search_dataset` 또는 `documents` 응답에서 `source_download_url`를 복사합니다.
2. 브라우저 또는 curl로 엽니다.

```bash
curl -I 'http://127.0.0.1:8090/_downloads/<token>'
```

기대:

- `200 OK`
- `Content-Disposition: attachment; filename="..."'`

## 7. Open WebUI 연결

### 7-1. User Tool Server

로컬 개발에서 가장 쉽습니다.

등록 URL:

- `http://localhost:8090`

절차:

1. Open WebUI Settings로 이동
2. Tools 또는 OpenAPI Tool Servers 메뉴로 이동
3. URL에 `http://localhost:8090` 입력
4. 저장 후 채팅에서 tool 활성화 확인

주의:

- User Tool Server는 브라우저가 직접 wrapper를 호출합니다.
- 따라서 브라우저에서 wrapper 주소가 열려야 합니다.
- CORS 설정이 맞아야 합니다.

### 7-2. Global Tool Server

운영 환경에서 권장합니다.

등록 URL 예시:

- 같은 Docker Compose 네트워크: `http://ow-ragflow-tool-server:8090`
- Docker에서 호스트 접근: `http://host.docker.internal:8090`
- 사내 reverse proxy: `https://ragflow-tools.company.internal`

주의:

- Global Tool Server는 Open WebUI 백엔드가 호출합니다.
- Docker 컨테이너 안에서 `localhost`는 컨테이너 자신입니다.
- 따라서 `http://localhost:8090`는 대부분 실패합니다.

## 8. WSL + Docker + Open WebUI 주의사항

### User Tool Server

- 브라우저 기준 주소를 씁니다.
- 일반적으로 `http://localhost:8090`이면 충분합니다.
- 안 되면 WSL IP 또는 reverse proxy URL을 사용합니다.

### Global Tool Server

- Open WebUI가 Docker 컨테이너면 `localhost`를 쓰면 안 됩니다.
- 우선순위:
  1. 같은 compose 네트워크의 서비스명
  2. `host.docker.internal`
  3. 사내 DNS 이름

### PUBLIC_BASE_URL

- 다운로드 링크와 응답 내 URL 생성에 사용됩니다.
- Open WebUI 사용자 브라우저가 실제로 여는 주소여야 합니다.
- User Tool Server면 보통 `http://localhost:8090`
- reverse proxy 운영이면 public DNS를 사용

## 9. Open WebUI에서 최종 확인할 질문

### dataset 명시 질문

예:

- `hr_handbook에서 연차 소멸 기준 알려줘`

기대:

- 모델이 `searchDataset` 우선 사용
- 답변 끝에 `sources` 기반 링크 표시

### dataset 불명 질문

예:

- `출장비 정산 기준 알려줘`

기대:

- `listDatasets` 또는 `searchAllDatasets` 사용

### 문서 목록 질문

예:

- `hr_handbook에 어떤 문서들이 있는지 보여줘`

기대:

- `listDatasetDocuments` 사용

## 10. 문제 발생 시 체크리스트

### `/health`가 실패하는 경우

- `RAGFLOW_BASE_URL`이 맞는지
- 사내 방화벽/프록시에서 wrapper -> RAGFlow outbound가 되는지
- API key 권한이 맞는지

### `/datasets`는 되는데 검색이 0건인 경우

- `config/datasets.yaml`의 `ragflow_name`이 실제 RAGFlow 이름과 일치하는지
- 해당 dataset이 실제로 chunking/indexing 완료 상태인지
- 질문이 너무 광범위하지 않은지

### 다운로드 링크가 안 열리는 경우

- `PUBLIC_BASE_URL`이 브라우저에서 접근 가능한 주소인지
- reverse proxy가 `/_downloads/*`를 wrapper로 전달하는지
- Open WebUI가 아니라 사용자 브라우저에서 해당 URL이 열리는지

### Open WebUI에서 tool이 안 붙는 경우

- `/openapi.json`이 열리는지
- User Tool Server인지 Global Tool Server인지에 맞는 URL을 썼는지
- Docker/WSL에서 `localhost` 함정에 걸리지 않았는지

## 11. 권장 운영 방식

- 개발/초기 검증:
  - User Tool Server
  - `PUBLIC_BASE_URL=http://localhost:8090`

- 운영:
  - reverse proxy 뒤에 wrapper 배치
  - Global Tool Server 등록
  - `PUBLIC_BASE_URL=https://ragflow-tools.company.internal`

## 12. 자동 테스트

이 저장소의 기본 자동 테스트는 fake RAGFlow client 기반입니다.

```bash
PYTHONPATH=. pytest
```

실제 RAGFlow live smoke는 위의 curl 절차로 별도 검증합니다.

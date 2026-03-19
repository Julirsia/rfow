# RAGFlow Read-Only OpenAPI Thin Wrapper

Open WebUI에서 소형 모델이 안정적으로 사용할 수 있도록 RAGFlow HTTP API를 읽기 전용 OpenAPI tool server로 감싼 thin wrapper 입니다.

핵심 원칙:

- RAGFlow API key는 서버 환경변수로만 사용합니다.
- 모델에는 `dataset_id`를 노출하지 않습니다.
- retrieval raw 파라미터는 숨기고 `question`, `dataset_name`, `top_k`만 받습니다.
- 응답에는 항상 근거 chunk와 원문 다운로드 링크를 포함합니다.
- write/delete/upload/parse control API는 노출하지 않습니다.

## 공개 엔드포인트

- `GET /health`
- `GET /datasets`
- `GET /datasets/{dataset_name}/documents`
- `POST /search_dataset`
- `POST /search_all`

비공개 다운로드 프록시:

- `GET /_downloads/{token}`

이 경로는 OpenAPI schema에 포함되지 않습니다.

## 실행

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8090
```

OpenAPI docs:

- `http://localhost:8090/docs`
- `http://localhost:8090/redoc`
- `http://localhost:8090/openapi.json`

사내 환경 설정과 실환경 smoke test 절차는 [docs/COMPANY_SETUP_AND_TEST.md](/Users/julirsia/development/company/ow-ragflow/docs/COMPANY_SETUP_AND_TEST.md)를 참고하세요.

## Dataset 설정

기본 파일은 `config/datasets.yaml` 입니다.

```yaml
datasets:
  - name: hr_handbook
    display_name: HR Handbook
    ragflow_name: HR Handbook
    aliases: ["hr", "handbook", "인사규정"]
    enabled: true
```

## Open WebUI 연결

로컬 개발 기본:

- User Tool Server URL: `http://localhost:8090`

운영 예시:

- Global Tool Server URL: `http://ow-ragflow-tool-server:8090`
- 또는 `https://ragflow-tools.internal.example.com`

주의:

- User Tool Server는 브라우저가 직접 호출하므로 CORS가 필요합니다.
- Global Tool Server에서 Docker/WSL 조합이면 `localhost` 대신 서비스명 또는 `host.docker.internal`을 사용해야 합니다.

## 테스트

이 저장소의 자동 테스트는 fake RAGFlow client 기반입니다.

```bash
PYTHONPATH=. pytest
```

실환경 smoke는 별도 env-gated 방식으로 추가하는 것을 권장합니다.

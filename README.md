# GitPreview AI

Solo-developer MVP for repository preview intelligence.

## Structure

- `backend/` — FastAPI backend
- `frontend/` — Next.js frontend
- `shared/` — shared TypeScript types

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```
### Features
```bash
- Repository metadata analysis
- Technology detection
- Folder structure analysis
- Entry point detection
- Important file detection
- AI generated repository summary
```

### Docker

```bash
docker compose up --build
```

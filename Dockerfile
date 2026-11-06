FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx vite build

FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY samples/ ./samples/
COPY --from=ui /ui/dist ./frontend/dist
ENV TP_DATA_DIR=/data TP_FRONTEND_DIST=/app/frontend/dist
VOLUME /data
EXPOSE 8000
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY frontend ./frontend
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --system planner
COPY spotter ./spotter
COPY --from=frontend /app/frontend/dist ./frontend/dist
USER planner
EXPOSE 8000
CMD ["sh", "-c", "exec gunicorn spotter.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 90"]

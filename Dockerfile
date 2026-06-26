# Image légère pour le Gold Macro Engine (API + scheduler).
# Multi-stage : build des deps puis runtime minimal.
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
# venv-less : on copie les paquets installés
COPY --from=build /install /usr/local
COPY app ./app
COPY demo.py README.md ./
# utilisateur non-root + dossier de données inscriptible (volume monté sur /data)
RUN useradd -m gold && mkdir -p /data && chown -R gold:gold /app /data
USER gold
# Le service (api ou scheduler) est choisi par docker-compose (command:).
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SUPPORTBOT_DB=/data/supportbot.sqlite3

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[all]"

COPY sample_kb ./sample_kb
COPY examples ./examples
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
VOLUME /data

CMD ["supportbot", "run", "telegram"]

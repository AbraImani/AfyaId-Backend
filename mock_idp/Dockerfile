FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py
COPY users.json /app/users.json
COPY bootstrap_keys.py /app/bootstrap_keys.py

ENV OIDC_ISSUER=http://localhost:9000
ENV OIDC_HOST=0.0.0.0
ENV OIDC_PORT=9000
ENV USERS_FILE=/app/users.json
ENV KEYS_DIR=/app/keys
ENV OIDC_CLIENT_ID=afya-local-client
ENV OIDC_CLIENT_SECRET=afya-local-secret
ENV OIDC_REDIRECT_URI=http://localhost:8000/auth/callback

EXPOSE 8080

CMD ["sh", "-c", "python /app/bootstrap_keys.py && uvicorn app:app --host ${OIDC_HOST} --port ${PORT:-${OIDC_PORT}}"]

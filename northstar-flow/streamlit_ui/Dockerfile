FROM python:3.11-slim

# Install dependencies for ODBC and SSL certificates
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    apt-transport-https \
    unixodbc-dev \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Import Microsoft GPG key and add repo
RUN curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor \
    | tee /usr/share/keyrings/microsoft-prod.gpg > /dev/null \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
    > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Set SSL certificate paths
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_DIR=/etc/ssl/certs
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV AZURE_AUTHORITY_HOST_CERTIFICATE_PATH=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# Copy project files and install dependencies
COPY pyproject.toml .
COPY uv.lock* .
RUN uv sync --frozen --no-dev

# Copy app code and config
COPY app.py .
COPY pages/ ./pages/
COPY components/ ./components/
COPY data/ ./data/
COPY .streamlit/ ./.streamlit/

EXPOSE 8501

# Set Python to run unbuffered
ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]

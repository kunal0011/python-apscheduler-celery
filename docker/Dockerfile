FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Install tox and tox-uv
RUN uv pip install --system tox tox-uv

# Copy dependency files
COPY pyproject.toml uv.toml tox.ini ./

# Copy application code (needed for tox to install)
COPY app/ ./app/
COPY migrations/ ./migrations/

# Create development environment with tox
RUN tox -re dev

# Set PATH to use tox dev environment
ENV PATH="/app/.tox/dev/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Default command
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]



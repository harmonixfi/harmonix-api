# Use an official Python runtime as a parent image
FROM python:3.10-alpine

# Set the timezone to UTC
RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime

# Update the package repository and install necessary dependencies
RUN apk update && apk add --no-cache \
    curl \
    bash \
    tzdata \
    build-base \
    linux-headers \
    libffi-dev \
    openssl-dev

WORKDIR /app/
# Install Poetry
RUN curl -sSL https://install.python-poetry.org -o install-poetry.py && \
    POETRY_HOME=/opt/poetry python3 install-poetry.py || (cat /app/poetry-installer-error-*.log && false) && \
    cd /usr/local/bin && \
    ln -s /opt/poetry/bin/poetry && \
    poetry config virtualenvs.create false

# Copy poetry.lock* in case it doesn't exist in the repo
COPY ./pyproject.toml /app/

# Allow installing dev dependencies to run tests
ARG INSTALL_DEV=false
RUN bash -c "if [ $INSTALL_DEV == 'true' ] ; then poetry install --no-root ; else poetry install --no-root --only main ; fi"

RUN pip install --force-reinstall httpcore==0.15
RUN pip install "uvicorn[standard]"

# Create logs directory if it doesn't exist
RUN mkdir -p /app-logs/

COPY ./src /app
ENV PYTHONPATH=/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
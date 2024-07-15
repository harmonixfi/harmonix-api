# Use an official Python runtime as a parent image
FROM python:3.10-alpine

# Set the timezone to UTC
RUN ln -sf /usr/share/zoneinfo/UTC /etc/localtime

# Update the package repository and install necessary dependencies
RUN apk update && apk add --no-cache curl bash tzdata build-base linux-headers

WORKDIR /app/

# Latest releases available at https://github.com/aptible/supercronic/releases
ENV SUPERCRONIC_URL=https://github.com/aptible/supercronic/releases/download/v0.2.30/supercronic-linux-arm \
    SUPERCRONIC=supercronic-linux-arm \
    SUPERCRONIC_SHA1SUM=9375e13dab716bab9f325de4a9145b482145f5e7

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 - && \
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

# Install Supercronic for ARM architecture
RUN curl -fsSLO "$SUPERCRONIC_URL" \
    && echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
    && chmod +x "$SUPERCRONIC" \
    && mv "$SUPERCRONIC" "/usr/local/bin/${SUPERCRONIC}" \
    && ln -s "/usr/local/bin/${SUPERCRONIC}" /usr/local/bin/supercronic

# Create logs directory if it doesn't exist
RUN mkdir -p /app-logs/

COPY ./src /app
ENV PYTHONPATH=/app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
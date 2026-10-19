FROM python:3.10-slim AS builder

# Install compiling dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gnupg curl ca-certificates && \
    sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt trixie-pgdg main" > /etc/apt/sources.list.d/pgdg.list' && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    mariadb-client \
    postgresql-client-14 \
    postgresql-client-15 \
    postgresql-client-16 \
    postgresql-client-17 \
    postgresql-client-18 \
    python3-dev libpq-dev gcc \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Create the virtual environment
RUN python -m venv /opt/venv

# Activate the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements file
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Use the official Python image from the Docker Hub
FROM python:3.10-slim AS prod


# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gnupg ca-certificates curl && \
    sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt trixie-pgdg main" > /etc/apt/sources.list.d/pgdg.list' && \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg && \
    apt-get update && \
    apt-get install -y --no-install-recommends gnupg curl ca-certificates && \
    case "$(dpkg --print-architecture)" in \
      amd64) mongodb_tools_url=https://fastdl.mongodb.org/tools/db/mongodb-database-tools-debian13-x86_64-100.19.1.deb ;; \
      arm64) mongodb_tools_url=https://fastdl.mongodb.org/tools/db/mongodb-database-tools-ubuntu2404-arm64-100.19.1.deb ;; \
      *) echo "Unsupported architecture for MongoDB Database Tools: $(dpkg --print-architecture)" >&2; exit 1 ;; \
    esac && \
    curl -fsSLo /tmp/mongodb-database-tools.deb "$mongodb_tools_url" && \
    apt-get install -y --no-install-recommends \
    dumb-init \
    mariadb-client \
    postgresql-client-14 \
    postgresql-client-15 \
    postgresql-client-16 \
    postgresql-client-17 \
    postgresql-client-18 \
    /tmp/mongodb-database-tools.deb \
    libpq-dev \
    docker-compose \
    && \
    rm -f /tmp/mongodb-database-tools.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*


# Set the working directory in the container
WORKDIR /app

# Copy the virtual environment from builder image
COPY --from=builder /opt/venv /opt/venv

# Activate the virtual environment
ENV PATH="/opt/venv/bin:$PATH"

# Copy the current directory contents into the container at /app
COPY . /app

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Use curl to healthcheck based on health endpoint
HEALTHCHECK --interval=60s --timeout=5s --start-period=5s --retries=12 \
  CMD curl -f http://127.0.0.1:5000/health || exit 1

# Use dumb-init as the entrypoint to handle signal forwarding and zombie reaping
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

# Run app.py when the container launches
CMD ["python", "app.py"]

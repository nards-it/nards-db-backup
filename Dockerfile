# Use the official Python image from the Docker Hub
FROM python:3.9-slim

# Install dumb-init
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    dumb-init \
    mariadb-client \
    postgresql-client \
    && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy requirements file
COPY requirements.txt /app/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Use curl to healthcheck based on health endpoint
HEALTHCHECK --interval=5s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://127.0.0.1:5000/health || exit 1

# Use dumb-init as the entrypoint to handle signal forwarding and zombie reaping
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

# Run app.py when the container launches
CMD ["python", "app.py"]
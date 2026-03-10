FROM python:3.12-slim

# Install system dependencies for theHarvester
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        gcc \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone theHarvester
RUN git clone --depth 1 https://github.com/laramies/theHarvester.git /opt/theHarvester

WORKDIR /opt/theHarvester

# Install theHarvester via pyproject.toml
RUN pip install --no-cache-dir .

# Create results mount point
RUN mkdir -p /results

VOLUME ["/results"]

# Default entrypoint is overridden to tail -f /dev/null in docker-compose
# so the container stays alive for docker exec commands
ENTRYPOINT ["theHarvester"]

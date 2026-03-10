FROM debian:bookworm-slim

# Install nmap, masscan, and Python for the nmap2json converter
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        nmap \
        masscan \
        python3 \
        python3-pip \
        curl \
        iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Create results mount point
RUN mkdir -p /results

# Copy utility scripts
COPY scripts/nmap2json.py /usr/local/bin/nmap2json.py
RUN chmod +x /usr/local/bin/nmap2json.py

VOLUME ["/results"]

# Default entrypoint is overridden to tail -f /dev/null in docker-compose
# so the container stays alive for docker exec commands
ENTRYPOINT ["nmap"]

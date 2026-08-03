ARG PGVECTOR_IMAGE=pgvector/pgvector:pg16@sha256:7d400e340efb42f4d8c9c12c6427adb253f726881a9985d2a471bf0eed824dff
FROM ${PGVECTOR_IMAGE}

USER root

# Apply currently available Debian fixes and remove the root-only privilege helper.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y --no-install-recommends \
    && rm -f /usr/local/bin/gosu \
    && rm -rf /var/lib/apt/lists/*

USER postgres

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" || exit 1

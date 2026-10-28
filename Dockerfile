# For scan / build / exhume. (The séance server binds to 127.0.0.1 by design,
# so run `git-ofrenda seance` natively rather than inside a container.)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory '*'
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV OFRENDA_CACHE=/cache
WORKDIR /repo
ENTRYPOINT ["git-ofrenda"]
# docker build -t git-ofrenda .
# docker run --rm -v "$PWD":/repo -v ofrenda-cache:/cache \
#   -e OFRENDA_HOST=http://host.docker.internal:11434 git-ofrenda build -o /repo/ofrenda.html

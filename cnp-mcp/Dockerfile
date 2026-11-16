FROM python:3.11-slim

WORKDIR /app

RUN useradd -m cnpmcp

# Dépendances d'abord (couche en cache), versions figées par requirements.lock.
COPY pyproject.toml requirements.lock ./
RUN mkdir cnp_mcp && touch cnp_mcp/__init__.py && \
    pip install --no-cache-dir -r requirements.lock && \
    pip install --no-cache-dir --no-deps -e .

COPY --chown=cnpmcp:cnpmcp cnp_mcp ./cnp_mcp

USER cnpmcp

EXPOSE 8080

CMD ["cnp-mcp"]

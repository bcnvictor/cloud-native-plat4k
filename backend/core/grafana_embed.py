"""JWT signés par le backend pour authentifier les iframes Grafana (ADR-0028).

Grafana vérifie la signature avec la clé publique (GF_AUTH_JWT_KEY_VALUE) et lit le
token dans le paramètre d'URL `auth_token` (GF_AUTH_JWT_URL_LOGIN).
"""

import base64
import logging
import time

from jose import jwt
from jose.exceptions import JOSEError

from backend.core.config import settings

logger = logging.getLogger(__name__)

GRAFANA_JWT_ISSUER = "cnp-backend"  # Doit correspondre à GF_AUTH_JWT_EXPECT_CLAIMS (docker-compose.yml)
GRAFANA_JWT_ALGORITHM = "ES256"


def create_grafana_embed_token(user_id: int) -> str | None:
    """JWT Viewer pour ce user CNP, ou None si l'embed n'est pas configuré.

    Le préfixe de `sub` empêche toute collision avec un compte Grafana existant
    (ex. `admin`), Grafana rattachant le token au compte de même login.
    """
    if not settings.GRAFANA_JWT_PRIVATE_KEY:
        return None
    now = int(time.time())
    claims = {
        "sub": f"cnp-user-{user_id}",
        "iss": GRAFANA_JWT_ISSUER,
        "role": "Viewer",
        "iat": now,
        "exp": now + settings.GRAFANA_JWT_TTL_MINUTES * 60,
    }
    try:
        private_key = base64.b64decode(settings.GRAFANA_JWT_PRIVATE_KEY, validate=True).decode()
        return jwt.encode(claims, private_key, algorithm=GRAFANA_JWT_ALGORITHM)
    except (ValueError, JOSEError) as e:
        # Seul le type est loggé : le message pourrait citer la clé.
        logger.error("Invalid GRAFANA_JWT_PRIVATE_KEY (%s)", type(e).__name__)
        return None

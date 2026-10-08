# Démo locale de l'assistant Plat4k

Outils de dev pour tester l'assistant IA en local, **jamais en production**.

```bash
# 1. Stack locale (modèle au quota séparé si gemini-flash-latest est épuisé)
AI_MODEL=gemini-flash-lite-latest docker compose up -d --build db backend frontend

# 2. Comptes et données de démo (idempotent)
docker compose exec -T backend python - < scripts/assistant-demo/seed.py

# 3. Faux Loki sur le port 3100 (logs réalistes pour demo-web / demo-api)
python3 scripts/assistant-demo/fake_loki.py
```

| Email | Mot de passe | Profil |
|---|---|---|
| admin@cnp.local | admin | admin plateforme |
| maintainer@cnp.local | maintainer | maintainer de Team Demo |
| dev@cnp.local | dev | developer de Team Demo |
| viewer@cnp.local | viewer | viewer de Team Demo, developer de Team Other |

Limites en local : pas de cluster enregistré (l'outil pods répond « pas de cluster cible »),
pas de projet GitLab lié aux apps de démo (l'outil CI répond « pas rattachée à un projet GitLab »).
Ces deux outils sont couverts par `backend/tests/test_assistant_diagnostics.py`.

Ne pas lancer `fake_loki.py` en même temps que `scripts/forward-ports.sh` (même port 3100).

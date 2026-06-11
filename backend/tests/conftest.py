"""Fixtures et configuration partagées entre tous les tests.

On positionne des variables d'environnement factices AVANT tout import de `backend.*`.
`backend.core.config.Settings` exige les paramètres POSTGRES_* et SECRET_KEY, et
`backend.db.session` construit un engine au moment de l'import. Sans ces valeurs,
le simple `pytest --collect-only` de la CI (qui importe les modules de test) échouerait.
Aucune connexion réelle n'est ouverte : les tests utilisent une base SQLite en mémoire.
"""

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

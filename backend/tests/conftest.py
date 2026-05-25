import pytest


# Fixtures partagées entre tous les tests.
# Exemple : client HTTP de test, base de données en mémoire, utilisateurs fixtures.
#
# Pour ajouter une fixture de client FastAPI (quand les tests seront écrits) :
#
#   from httpx import AsyncClient
#   from backend.main import app
#
#   @pytest.fixture
#   async def client():
#       async with AsyncClient(app=app, base_url="http://test") as c:
#           yield c

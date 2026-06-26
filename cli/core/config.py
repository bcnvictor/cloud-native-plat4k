import toml
from pathlib import Path

CONFIG_DIR = Path.home() / ".cnp"
CONFIG_FILE = CONFIG_DIR / "config.toml"

# URL publique de la documentation CNP (Cloudflare Pages).
# Externalisée ici pour découpler l'URL de la commande `cnp docs`.
DOCS_URL = "https://cnp-docs.pages.dev"

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE, "r") as f:
        return toml.load(f)

def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        toml.dump(config, f)

def get_base_url():
    config = load_config()
    return config.get("api_url", "http://localhost:8000/api/v1")

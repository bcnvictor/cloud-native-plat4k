import os
import tempfile

# cli.core.client builds its APIClient at import time from ~/.cnp/config.toml:
# point HOME at an empty directory first so tests never load a real API key/URL.
os.environ["HOME"] = tempfile.mkdtemp(prefix="cnp-cli-tests-")

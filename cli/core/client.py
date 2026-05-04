import requests
from cli.core.config import load_config, get_base_url

class APIClient:
    def __init__(self):
        self.base_url = get_base_url()
        self.config = load_config()
        self.api_key = self.config.get("api_key")
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({"X-API-Key": self.api_key})

    def _handle_response(self, response: requests.Response):
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            msg = f"HTTP Error: {e}"
            try:
                err_data = response.json()
                if "detail" in err_data:
                    msg = f"Error: {err_data['detail']}"
            except Exception:
                pass
            raise Exception(msg)

    def get(self, endpoint: str, params=None):
        res = self.session.get(f"{self.base_url}{endpoint}", params=params)
        return self._handle_response(res)

    def post(self, endpoint: str, json=None, data=None):
        res = self.session.post(f"{self.base_url}{endpoint}", json=json, data=data)
        return self._handle_response(res)

    def delete(self, endpoint: str):
        res = self.session.delete(f"{self.base_url}{endpoint}")
        return self._handle_response(res)

client = APIClient()

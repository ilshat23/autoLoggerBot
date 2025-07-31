import requests as req  # type: ignore


class TelegramClient:

    def __init__(self, api_token: str, base_url: str):
        self.api_token = api_token
        self.base_url = base_url

    def _prepare_url(self, method: str):
        full_url = f'{self.base_url}/bot{self.api_token}/'

        if method is not None:
            full_url += method

        return full_url

    def post(self, method: str = None, params: dict = None,
             body: dict | None = None):

        url = self._prepare_url(method)
        response = req.post(url, params=params, data=body)

        return response.json()

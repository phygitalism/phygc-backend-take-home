"""Thin client for the Acme Generative API (docs/provider_api.md)."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger("genpipe.provider")


class ProviderError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(f"provider responded {status_code}: {message}")
        self.status_code = status_code
        self.message = message


def _log_request(request: httpx.Request) -> None:
    logger.info(
        "provider request %s %s headers=%s",
        request.method,
        request.url,
        dict(request.headers),
    )


def _log_response(response: httpx.Response) -> None:
    logger.info("provider response %s %s", response.status_code, response.request.url)


class ProviderClient:
    def __init__(self, base_url: str, api_key: str):
        # Generations can be slow, do not cut the provider off.
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=None,
            event_hooks={"request": [_log_request], "response": [_log_response]},
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        response = self._http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ProviderError(response.status_code, response.text)
        return response.json()

    def create_generation(
        self, *, model: str, prompt: str, num_outputs: int, webhook_url: str
    ) -> dict:
        return self._request(
            "POST",
            "/v1/generations",
            json={
                "model": model,
                "prompt": prompt,
                "num_outputs": num_outputs,
                "webhook_url": webhook_url,
            },
        )

    def get_generation(self, generation_id: str) -> dict:
        return self._request("GET", f"/v1/generations/{generation_id}")

    def list_models(self) -> dict:
        return self._request("GET", "/v1/models")


provider = ProviderClient(settings.provider_base_url, settings.provider_api_key)

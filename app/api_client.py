from __future__ import annotations

from typing import Any

import requests


class BackendApiError(RuntimeError):
    pass


class BackendApiClient:
    def __init__(self, base_url: str, timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise BackendApiError("Backend returned a non-JSON response") from exc

        if response.status_code >= 400:
            raise BackendApiError(payload.get("error", "Backend request failed"))
        return payload

    def authenticate_user(self, telegram_user: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/auth/telegram", json=telegram_user)

    def get_user_profile(self, telegram_id: int) -> dict[str, Any]:
        return self._request("GET", f"/users/{telegram_id}")

    def get_available_numbers(self) -> dict[str, Any]:
        return self._request("GET", "/numbers")

    def save_selected_number(self, telegram_id: int, selected_number: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/users/{telegram_id}/selected-number",
            json={"selected_number": selected_number},
        )

    def place_call(self, telegram_id: int, source_number: str, destination_number: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/calls",
            json={
                "telegram_id": telegram_id,
                "source_number": source_number,
                "destination_number": destination_number,
            },
        )

    def get_call_status(self, call_id: str) -> dict[str, Any]:
        return self._request("GET", f"/calls/{call_id}")

    def end_call(self, call_id: str) -> dict[str, Any]:
        return self._request("POST", f"/calls/{call_id}/end")

    def get_call_history(self, telegram_id: int) -> dict[str, Any]:
        return self._request("GET", f"/users/{telegram_id}/calls")

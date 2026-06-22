"""Linear GraphQL API client with rate-limit awareness and constraint discovery."""

import os
import time
import httpx
from typing import Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from agent.memory.capability_store import add_constraint

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearAPIError(Exception):
    def __init__(self, message: str, errors: Optional[list] = None, status_code: int = 0):
        super().__init__(message)
        self.errors = errors or []
        self.status_code = status_code


class RateLimitError(LinearAPIError):
    pass


class LinearClient:
    def __init__(self):
        self.api_key = os.getenv("LINEAR_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("LINEAR_API_KEY not set")
        self._call_count = 0
        self._last_reset = time.time()

    @property
    def call_count(self) -> int:
        return self._call_count

    def reset_call_count(self) -> None:
        self._call_count = 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(RateLimitError),
    )
    def execute(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query/mutation. Returns the `data` dict."""
        self._call_count += 1
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = httpx.post(
                LINEAR_API_URL, json=payload, headers=headers, timeout=30
            )
        except httpx.TimeoutException as e:
            raise LinearAPIError(f"Request timed out: {e}")

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            add_constraint("linear_api", "rate_limit", f"429 received; Retry-After={retry_after}s")
            time.sleep(retry_after)
            raise RateLimitError("Rate limited by Linear API")

        if response.status_code >= 500:
            raise LinearAPIError(f"Linear server error: {response.status_code}", status_code=response.status_code)

        body = response.json()

        if "errors" in body and body["errors"]:
            errors = body["errors"]
            messages = [e.get("message", "") for e in errors]

            # Discover and persist constraints from API errors
            for msg in messages:
                if "permission" in msg.lower() or "forbidden" in msg.lower():
                    add_constraint("linear_api", "permission", msg)
                elif "not found" in msg.lower():
                    add_constraint("linear_api", "not_found", msg)
                elif "validation" in msg.lower() or "invalid" in msg.lower():
                    add_constraint("linear_api", "validation", msg)

            raise LinearAPIError(
                f"GraphQL errors: {'; '.join(messages)}", errors=errors
            )

        return body.get("data", {})

    def introspect_type(self, type_name: str) -> dict:
        """Fetch the GraphQL schema for a specific type — used by capability synthesis."""
        query = """
        query IntrospectType($name: String!) {
          __type(name: $name) {
            name
            fields {
              name
              description
              type { name kind ofType { name kind } }
            }
            inputFields {
              name
              description
              type { name kind ofType { name kind } }
            }
          }
        }
        """
        return self.execute(query, {"name": type_name})

    def get_available_mutations(self) -> list[dict]:
        """Introspect the Mutation type to discover available operations."""
        query = """
        {
          __type(name: "Mutation") {
            fields {
              name
              description
              args { name description type { name kind ofType { name kind } } }
            }
          }
        }
        """
        data = self.execute(query)
        return data.get("__type", {}).get("fields", [])

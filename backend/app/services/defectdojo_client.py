"""REST API client for the DefectDojo vulnerability management platform.

Uses ``httpx.AsyncClient`` for all HTTP communication.  Provides helpers
to create products, engagements, and import scan results.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DefectDojoClient:
    """Async wrapper around the DefectDojo v2 REST API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url: str = base_url.rstrip("/")
        self.api_key: str = api_key
        self.headers: dict[str, str] = {
            "Authorization": f"Token {api_key}",
            "Content-Type": "application/json",
        }
        self.client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=60.0,
        )

    # ── Products ─────────────────────────────────────────────────────────

    async def get_or_create_product(self, name: str, prod_type_id: int = 1) -> int:
        """Return the DefectDojo product ID, creating the product if it does not exist."""
        try:
            resp = await self.client.get("/api/v2/products/", params={"name": name})
            resp.raise_for_status()
            data = resp.json()
            if data.get("count", 0) > 0:
                product_id: int = data["results"][0]["id"]
                logger.info("Found existing DefectDojo product '%s' (id=%d)", name, product_id)
                return product_id
        except httpx.HTTPStatusError as exc:
            logger.warning("Error searching for product '%s': %s", name, exc)

        # Product does not exist yet — create it.
        resp = await self.client.post(
            "/api/v2/products/",
            json={
                "name": name,
                "description": "Automated security assessment",
                "prod_type": prod_type_id,
            },
        )
        resp.raise_for_status()
        product_id = resp.json()["id"]
        logger.info("Created DefectDojo product '%s' (id=%d)", name, product_id)
        return product_id

    # ── Engagements ──────────────────────────────────────────────────────

    async def create_engagement(self, product_id: int, name: str) -> int:
        """Create a new engagement for a scan run."""
        today = date.today().isoformat()
        resp = await self.client.post(
            "/api/v2/engagements/",
            json={
                "name": name,
                "product": product_id,
                "target_start": today,
                "target_end": today,
                "engagement_type": "CI/CD",
                "status": "In Progress",
            },
        )
        resp.raise_for_status()
        engagement_id: int = resp.json()["id"]
        logger.info("Created DefectDojo engagement '%s' (id=%d) for product %d", name, engagement_id, product_id)
        return engagement_id

    # ── Scan import ──────────────────────────────────────────────────────

    async def import_scan(
        self,
        engagement_id: int,
        scan_type: str,
        file_content: bytes,
        filename: str,
    ) -> dict[str, Any]:
        """Import scan results into DefectDojo via multipart form upload.

        ``scan_type`` must match a DefectDojo-supported scan type string,
        for example ``"Nuclei Scan"``, ``"ZAP Scan"``, ``"Nmap Scan"``.
        """
        files = {"file": (filename, file_content)}
        data: dict[str, str] = {
            "engagement": str(engagement_id),
            "scan_type": scan_type,
            "active": "true",
            "verified": "false",
        }

        # Use a dedicated client without the JSON Content-Type header so that
        # httpx can properly set the multipart boundary.
        async with httpx.AsyncClient(base_url=self.base_url, timeout=120.0) as upload_client:
            resp = await upload_client.post(
                "/api/v2/import-scan/",
                headers={"Authorization": f"Token {self.api_key}"},
                data=data,
                files=files,
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            logger.info(
                "Imported %s (%s) into engagement %d — test_id=%s",
                filename,
                scan_type,
                engagement_id,
                result.get("test"),
            )
            return result

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close the underlying httpx client."""
        await self.client.aclose()

"""
Supabase Storage client for in-memory evidence PDF uploads and signed URL generation.

Uses httpx.AsyncClient to communicate with the Supabase Storage REST API.
No local files or disk buffers are created during uploads or downloads.
"""

from __future__ import annotations

import logging
from typing import Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class SupabaseStorageError(Exception):
    """Raised when Supabase Storage operations fail."""
    pass


class SupabaseStorageService:
    """
    Async client for Supabase Storage.
    Manages bucket creation, in-memory PDF uploads, and short-lived signed URLs.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        service_role_key: Optional[str] = None,
        default_bucket: Optional[str] = None,
    ) -> None:
        self.supabase_url = (supabase_url or settings.supabase_url).rstrip("/")
        self.service_role_key = service_role_key or settings.supabase_service_role_key
        self.default_bucket = default_bucket or settings.supabase_storage_bucket
        self._client: Optional[httpx.AsyncClient] = None

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
        }
        return headers

    async def _client_session(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers=self._get_headers() if self.service_role_key else {},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def ensure_bucket(self, bucket_name: Optional[str] = None) -> bool:
        """
        Ensure the target storage bucket exists; creates it as a private bucket if missing.
        """
        bucket = bucket_name or self.default_bucket
        if not self.service_role_key:
            logger.warning("Supabase service role key not configured. Skipping bucket check.")
            return True

        client = await self._client_session()
        url = f"{self.supabase_url}/storage/v1/bucket/{bucket}"

        try:
            resp = await client.get(url, headers=self._get_headers())
            if resp.status_code == 200:
                return True
            elif resp.status_code == 404:
                # Create bucket
                create_url = f"{self.supabase_url}/storage/v1/bucket"
                create_resp = await client.post(
                    create_url,
                    headers=self._get_headers(),
                    json={
                        "id": bucket,
                        "name": bucket,
                        "public": False,
                        "file_size_limit": 10485760,  # 10 MB limit
                        "allowed_mime_types": ["application/pdf"],
                    },
                )
                if create_resp.status_code in (200, 201):
                    logger.info("Created Supabase Storage bucket: %s", bucket)
                    return True
                else:
                    logger.error(
                        "Failed to create Supabase Storage bucket %s: %s",
                        bucket,
                        create_resp.text,
                    )
                    return False
            else:
                logger.warning(
                    "Unexpected status checking Supabase bucket %s: HTTP %d",
                    bucket,
                    resp.status_code,
                )
                return False
        except Exception as exc:
            logger.exception("Error checking/creating Supabase bucket %s: %s", bucket, exc)
            return False

    async def upload_evidence_pdf(
        self,
        dispute_id: str,
        pdf_bytes: bytes,
        bucket_name: Optional[str] = None,
    ) -> str:
        """
        Upload in-memory PDF bytes to Supabase Storage.
        Returns the canonical storage_path: '{bucket}/{dispute_id}/evidence.pdf'
        """
        bucket = bucket_name or self.default_bucket
        object_path = f"{dispute_id}/evidence.pdf"
        storage_path = f"{bucket}/{object_path}"

        if not self.service_role_key:
            # Fallback mock path for tests or environments without credentials
            logger.warning(
                "Supabase service role key not provided. Storing mock pointer: %s",
                storage_path,
            )
            return storage_path

        client = await self._client_session()
        upload_url = f"{self.supabase_url}/storage/v1/object/{bucket}/{object_path}"

        headers = self._get_headers()
        headers["Content-Type"] = "application/pdf"
        headers["x-upsert"] = "true"

        try:
            resp = await client.post(
                upload_url,
                headers=headers,
                content=pdf_bytes,
            )
            if resp.status_code in (200, 201):
                logger.info(
                    "Uploaded in-memory PDF (%d bytes) to Supabase: %s",
                    len(pdf_bytes),
                    storage_path,
                )
                return storage_path
            else:
                logger.error(
                    "Supabase upload failed: HTTP %d — %s",
                    resp.status_code,
                    resp.text,
                )
                raise SupabaseStorageError(
                    f"Supabase upload failed with HTTP {resp.status_code}: {resp.text}"
                )
        except httpx.RequestError as exc:
            logger.exception("Network error uploading evidence to Supabase: %s", exc)
            raise SupabaseStorageError(f"Network error during Supabase upload: {exc}") from exc

    async def create_signed_url(
        self,
        storage_path: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a short-lived signed URL for the given storage_path.
        storage_path format: '{bucket}/{object_path}'
        """
        parts = storage_path.split("/", 1)
        if len(parts) != 2:
            raise SupabaseStorageError(f"Invalid storage_path format: {storage_path}")

        bucket, object_path = parts[0], parts[1]

        if not self.service_role_key:
            # Fallback for mock environments
            return f"{self.supabase_url}/storage/v1/object/public/{storage_path}?mock_token=signed_{expires_in}s"

        client = await self._client_session()
        sign_url = f"{self.supabase_url}/storage/v1/object/sign/{bucket}/{object_path}"

        try:
            resp = await client.post(
                sign_url,
                headers=self._get_headers(),
                json={"expiresIn": expires_in},
            )
            if resp.status_code == 200:
                data = resp.json()
                signed_rel = data.get("signedURL")
                if not signed_rel:
                    raise SupabaseStorageError("Signed URL response missing signedURL field")
                
                # Supabase returns "/object/sign/..." or full path
                if signed_rel.startswith("http"):
                    return signed_rel
                elif signed_rel.startswith("/storage/v1"):
                    return f"{self.supabase_url}{signed_rel}"
                elif signed_rel.startswith("/"):
                    return f"{self.supabase_url}/storage/v1{signed_rel}"
                else:
                    return f"{self.supabase_url}/storage/v1/{signed_rel}"
            else:
                raise SupabaseStorageError(
                    f"Failed to generate signed URL (HTTP {resp.status_code}): {resp.text}"
                )
        except httpx.RequestError as exc:
            logger.exception("Network error requesting signed URL: %s", exc)
            raise SupabaseStorageError(f"Network error requesting signed URL: {exc}") from exc


    async def purge_evidence_bucket(self, bucket_name: Optional[str] = None) -> int:
        """
        Delete all stored PDF evidence files from the Supabase Storage bucket.
        Attempts to empty the bucket via Supabase Storage API, and falls back to listing
        and deleting objects.
        Returns the number of deleted files or 0 if empty/mock.
        """
        bucket = bucket_name or self.default_bucket
        if not self.service_role_key:
            logger.info("Supabase service role key not configured. Mock storage purge complete for %s.", bucket)
            return 0

        client = await self._client_session()
        deleted_count = 0

        # Attempt 1: POST /storage/v1/bucket/{bucket}/empty
        try:
            empty_url = f"{self.supabase_url}/storage/v1/bucket/{bucket}/empty"
            resp = await client.post(empty_url, headers=self._get_headers())
            if resp.status_code in (200, 201, 204):
                logger.info("Successfully emptied Supabase Storage bucket %s via empty API endpoint.", bucket)
                return 1
            else:
                logger.debug("Empty bucket API returned HTTP %d: %s. Falling back to object listing...", resp.status_code, resp.text)
        except Exception as exc:
            logger.debug("Empty bucket API failed (%s). Falling back to object listing...", exc)

        # Attempt 2: List and delete objects
        try:
            list_url = f"{self.supabase_url}/storage/v1/object/list/{bucket}"
            resp = await client.post(
                list_url,
                headers=self._get_headers(),
                json={"prefix": "", "limit": 1000, "offset": 0, "sortBy": {"column": "name", "order": "asc"}},
            )
            if resp.status_code == 200:
                items = resp.json()
                prefixes_to_delete: list[str] = []
                for item in items:
                    name = item.get("name")
                    if not name:
                        continue
                    # Check if item is an object or folder
                    if item.get("id") is None and "metadata" not in item:
                        # Subfolder: list objects inside subfolder
                        sub_resp = await client.post(
                            list_url,
                            headers=self._get_headers(),
                            json={"prefix": f"{name}/", "limit": 100},
                        )
                        if sub_resp.status_code == 200:
                            sub_items = sub_resp.json()
                            for sub_item in sub_items:
                                sub_name = sub_item.get("name")
                                if sub_name:
                                    prefixes_to_delete.append(f"{name}/{sub_name}")
                        prefixes_to_delete.append(name)
                    else:
                        prefixes_to_delete.append(name)

                if prefixes_to_delete:
                    delete_url = f"{self.supabase_url}/storage/v1/object/{bucket}"
                    del_resp = await client.request(
                        "DELETE",
                        delete_url,
                        headers=self._get_headers(),
                        json={"prefixes": prefixes_to_delete},
                    )
                    if del_resp.status_code in (200, 204):
                        deleted_count = len(prefixes_to_delete)
                        logger.info("Purged %d objects from Supabase Storage bucket %s", deleted_count, bucket)
                    else:
                        logger.warning("Object deletion returned HTTP %d: %s", del_resp.status_code, del_resp.text)
            elif resp.status_code == 404:
                logger.info("Storage bucket %s does not exist or is already empty.", bucket)
            else:
                logger.warning("Listing storage objects returned HTTP %d: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Error during Supabase object listing/deletion for %s: %s", bucket, exc)

        return deleted_count


# Singleton instance
storage_service = SupabaseStorageService()

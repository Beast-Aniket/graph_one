import asyncio
from datetime import UTC, datetime
import hashlib
import boto3
from botocore.client import Config
from graphone.config import get_settings


class ObjectStorage:
    def __init__(self) -> None:
        settings = get_settings()
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            config=Config(s3={"addressing_style": "path"}),
        )

    async def ensure_bucket(self) -> None:
        def create() -> None:
            buckets = {item["Name"] for item in self.client.list_buckets().get("Buckets", [])}
            if self.bucket not in buckets:
                self.client.create_bucket(Bucket=self.bucket)

        await asyncio.to_thread(create)

    async def put_raw(self, source_id: str, content: bytes, content_type: str | None) -> tuple[str, str]:
        digest = hashlib.sha256(content).hexdigest()
        key = f"raw/{datetime.now(UTC):%Y/%m/%d}/{source_id}/{digest}.bin"
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type or "application/octet-stream",
            Metadata={"sha256": digest},
        )
        return key, digest


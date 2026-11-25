"""S3 and SQS access. Data never passes through the API: uploads/downloads use presigned URLs."""

import asyncio
import json
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from opentelemetry import propagate, trace

from app.config import get_settings

tracer = trace.get_tracer("dlp-api")


def _client(service: str, endpoint: str | None):
    s = get_settings()
    kwargs: dict = {"region_name": s.aws_region}
    if service == "s3":
        # In AWS use the regional endpoint with virtual-hosted style: the global endpoint answers 307 for new
        # buckets, which browsers cannot follow for a cross-origin presigned PUT.
        endpoint = endpoint or f"https://s3.{s.aws_region}.amazonaws.com"
        kwargs["config"] = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path" if get_settings().aws_endpoint_url else "virtual"},
        )
    return boto3.client(service, endpoint_url=endpoint, **kwargs)


@lru_cache
def s3():
    return _client("s3", get_settings().aws_endpoint_url)


@lru_cache
def s3_presigner():
    """Presign against the endpoint the browser can reach (differs from the internal one locally)."""
    s = get_settings()
    return _client("s3", s.s3_public_endpoint_url or s.aws_endpoint_url)


@lru_cache
def sqs():
    return _client("sqs", get_settings().aws_endpoint_url)


@lru_cache
def queue_url() -> str:
    return sqs().get_queue_url(QueueName=get_settings().sqs_queue_name)["QueueUrl"]


def presign_put(key: str, content_type: str, size: int) -> str:
    s = get_settings()
    return s3_presigner().generate_presigned_url(
        "put_object",
        Params={"Bucket": s.s3_bucket, "Key": key, "ContentType": content_type, "ContentLength": size},
        ExpiresIn=s.upload_url_ttl,
    )


def presign_get(key: str, filename: str) -> str:
    s = get_settings()
    return s3_presigner().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": s.s3_bucket,
            "Key": key,
            "ResponseContentDisposition": f'attachment; filename="{filename}"',
        },
        ExpiresIn=s.download_url_ttl,
    )


def head_size(key: str) -> int | None:
    try:
        return s3().head_object(Bucket=get_settings().s3_bucket, Key=key)["ContentLength"]
    except ClientError:
        return None


def read_head(key: str, nbytes: int = 4096) -> str:
    """First bytes of an object; only used for the already-redacted preview."""
    try:
        obj = s3().get_object(Bucket=get_settings().s3_bucket, Key=key, Range=f"bytes=0-{nbytes - 1}")
    except ClientError:
        return "(preview unavailable)"
    return obj["Body"].read().decode("utf-8", errors="replace")


def send_scan(payload: dict) -> None:
    carrier: dict[str, str] = {}
    with tracer.start_as_current_span("sqs.send", kind=trace.SpanKind.PRODUCER):
        propagate.inject(carrier)  # W3C traceparent travels in message attributes
        attrs = {k: {"DataType": "String", "StringValue": v} for k, v in carrier.items()}
        sqs().send_message(QueueUrl=queue_url(), MessageBody=json.dumps(payload), MessageAttributes=attrs)


async def run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def bootstrap() -> None:
    """Create bucket, queue and DLQ against local stand-ins (moto). Terraform owns this in AWS."""
    s = get_settings()
    try:
        s3().create_bucket(
            Bucket=s.s3_bucket, CreateBucketConfiguration={"LocationConstraint": s.aws_region}
        )
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    dlq = sqs().create_queue(QueueName=f"{s.sqs_queue_name}-dlq")["QueueUrl"]
    dlq_arn = sqs().get_queue_attributes(QueueUrl=dlq, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sqs().create_queue(
        QueueName=s.sqs_queue_name,
        Attributes={
            "VisibilityTimeout": str(s.sqs_visibility_timeout),
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": 3}),
        },
    )

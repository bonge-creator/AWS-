"""boto3 client factory.

Credentials come from validated settings (which read .env), not os.environ, so
the app and Alembic behave the same. If settings carry no keys, boto3's default
chain (instance/role credentials) applies — this is how it runs on Lambda/EC2.
"""

import boto3
from botocore.config import Config

from app.core.config import settings


def aws_client(service: str, *, max_attempts: int = 6):
    """Create a boto3 client from validated settings.

    `max_attempts` is the botocore-level retry budget. Callers that do their
    own retrying — because they can tell a throttle that clears in seconds
    from one that cannot clear at all — should pass a smaller budget so the
    decision is made once, in one place, with the error in hand.
    """
    session = boto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_session_token=settings.aws_session_token,
        region_name=settings.aws_region,
    )
    return session.client(
        service,
        config=Config(
            # Adaptive mode backs off on Bedrock throttling instead of failing the request.
            retries={"max_attempts": max_attempts, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=60,
        ),
    )

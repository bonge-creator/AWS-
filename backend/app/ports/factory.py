"""Provider factory — selects AWS or local adapters from env config.

AWS adapters are the default. Local adapters are real implementations used only
where the sandbox denies the AWS service (see docs/deviations in the README).
"""

from functools import lru_cache

from app.core.config import settings
from app.ports.embedder import EmbedderPort
from app.ports.extractor import ExtractorPort
from app.ports.jobs import JobRunnerPort
from app.ports.llm import LlmPort
from app.ports.storage import StoragePort


@lru_cache
def get_storage() -> StoragePort:
    if settings.storage_impl == "s3" and settings.s3_bucket_name:
        from app.ports.aws import S3StorageAdapter

        return S3StorageAdapter(bucket=settings.s3_bucket_name, kms_key_id=settings.s3_kms_key_id)
    from app.ports.local import LocalStorageAdapter

    return LocalStorageAdapter()


@lru_cache
def get_extractor() -> ExtractorPort:
    if settings.extractor_impl == "textract":
        from app.ports.aws import TextractExtractorAdapter

        return TextractExtractorAdapter()
    from app.ports.local import MultiFormatExtractorAdapter

    return MultiFormatExtractorAdapter()


@lru_cache
def get_embedder() -> EmbedderPort:
    if settings.embedder_impl == "titan-v2":
        from app.ports.aws import BedrockTitanEmbedderAdapter

        return BedrockTitanEmbedderAdapter(model_id=settings.bedrock_embed_model_id)
    if settings.embedder_impl == "bge-m3":
        from app.ports.local import BgeM3EmbedderAdapter

        return BgeM3EmbedderAdapter()
    from app.ports.local import HashEmbedderAdapter

    return HashEmbedderAdapter()


@lru_cache
def get_llm() -> LlmPort:
    from app.ports.local import ExtractiveLlmAdapter

    if settings.llm_impl == "bedrock-converse":
        from app.ports.aws import BedrockConverseLlmAdapter
        from app.ports.fallback import FallbackLlmAdapter

        fallbacks = [
            m.strip()
            for m in settings.bedrock_fallback_model_ids.split(",")
            if m.strip()
        ]
        return FallbackLlmAdapter(
            BedrockConverseLlmAdapter(
                model_id=settings.bedrock_model_id, fallback_models=fallbacks
            ),
            ExtractiveLlmAdapter(),
        )
    return ExtractiveLlmAdapter()


@lru_cache
def get_job_runner() -> JobRunnerPort:
    from app.ports.local_jobs import LocalJobRunner

    return LocalJobRunner()

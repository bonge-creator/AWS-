"""Checks that each AWS service the app uses is reachable with the .env settings."""
import json
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config


def load_env(path=".env"):
    env = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


E = load_env()
region = E.get("AWS_REGION", "us-east-1")
kw = dict(region_name=region,
          config=Config(retries={"max_attempts": 1}, connect_timeout=10, read_timeout=40))
if E.get("AWS_ACCESS_KEY_ID"):
    kw["aws_access_key_id"] = E["AWS_ACCESS_KEY_ID"]
    kw["aws_secret_access_key"] = E.get("AWS_SECRET_ACCESS_KEY", "")
    if E.get("AWS_SESSION_TOKEN"):
        kw["aws_session_token"] = E["AWS_SESSION_TOKEN"]


def check(name, fn):
    try:
        print(f"OK    {name}: {fn()}")
    except Exception as e:
        print(f"FAIL  {name}: {type(e).__name__}: {str(e)[:220]}")


def whoami():
    return boto3.client("sts", **kw).get_caller_identity()["Arn"]


def s3_test():
    bucket = E["S3_BUCKET_NAME"]
    c = boto3.client("s3", **kw)
    key = "healthcheck/test.txt"
    c.put_object(Bucket=bucket, Key=key, Body=b"ok")
    assert c.get_object(Bucket=bucket, Key=key)["Body"].read() == b"ok"
    c.delete_object(Bucket=bucket, Key=key)
    return f"write/read/delete on {bucket}"


def llm(model_id):
    def run():
        r = boto3.client("bedrock-runtime", **kw).converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with the word OK."}]}],
            inferenceConfig={"maxTokens": 10},
        )
        return r["output"]["message"]["content"][0]["text"].strip()
    return run


def titan():
    r = boto3.client("bedrock-runtime", **kw).invoke_model(
        modelId=E["BEDROCK_EMBED_MODEL_ID"],
        body=json.dumps({"inputText": "hello", "dimensions": 1024, "normalize": True}),
    )
    return f"{len(json.loads(r['body'].read())['embedding'])}-dim vector"


def cognito():
    url = (f"https://cognito-idp.{E['COGNITO_REGION']}.amazonaws.com/"
           f"{E['COGNITO_USER_POOL_ID']}/.well-known/jwks.json")
    return f"signing keys published (HTTP {urllib.request.urlopen(url, timeout=10).status})"


print(f"Region: {region}\n")
check("Credentials (STS)", whoami)
if E.get("S3_BUCKET_NAME"):
    check("S3", s3_test)
models = [E.get("BEDROCK_MODEL_ID", "")] + E.get("BEDROCK_FALLBACK_MODEL_IDS", "").split(",")
for m in [m.strip() for m in models if m.strip()]:
    check(f"Bedrock generation {m}", llm(m))
if E.get("BEDROCK_EMBED_MODEL_ID"):
    check(f"Bedrock embeddings {E['BEDROCK_EMBED_MODEL_ID']}", titan)
if E.get("COGNITO_USER_POOL_ID"):
    check("Cognito", cognito)
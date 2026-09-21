"""Shared helpers for the AI batch jobs: Azure OpenAI client, vector encoding.

Every model output is computed here in batch and stored in SQL; the website
never calls a model while someone is using it.
"""
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "etl"))
load_dotenv(ROOT / ".env")

API_VERSION = "2024-10-21"
EMBED_DIMS = 1536
# USD per 1M tokens, for the printed cost estimates only.
PRICE_EMBED = 0.02
PRICE_CHAT_IN, PRICE_CHAT_OUT = 0.40, 1.60


def openai_client():
    from openai import AzureOpenAI
    return AzureOpenAI(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                       api_key=os.environ["AZURE_OPENAI_KEY"],
                       api_version=API_VERSION, max_retries=8, timeout=60)


def embed_deployment() -> str:
    return os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"]


def chat_deployment() -> str:
    return os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]


def to_bytes(vec) -> bytes:
    """float32 little-endian, 1536 x 4 = 6,144 bytes per vector."""
    a = np.asarray(vec, dtype="<f4")
    assert a.shape == (EMBED_DIMS,), a.shape
    return a.tobytes()


def from_bytes(b: bytes) -> np.ndarray:
    a = np.frombuffer(bytes(b), dtype="<f4")
    assert a.shape == (EMBED_DIMS,), a.shape
    return a


def hex_literal(b: bytes) -> str:
    return "0x" + b.hex()


def search_client_args(service: str):
    """(endpoint, AzureKeyCredential) for SEARCH / DOCINTEL / LANGUAGE."""
    from azure.core.credentials import AzureKeyCredential
    return os.environ[f"AZURE_{service}_ENDPOINT"], AzureKeyCredential(os.environ[f"AZURE_{service}_KEY"])

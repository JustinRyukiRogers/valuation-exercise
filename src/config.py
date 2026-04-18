"""Configuration loader — reads .env and peer_set.yaml into typed objects."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# Project root = parent of src/
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
METRICS_DIR = DATA_DIR / "metrics"
CHARTS_DIR = DATA_DIR / "charts"

# Ensure data dirs exist on import
for d in (RAW_DIR, CACHE_DIR, METRICS_DIR, CHARTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Load .env once (no-op if missing)
load_dotenv(ROOT / ".env")


@dataclass
class Peer:
    """A single project in the peer set."""
    symbol: str
    name: str
    category: str
    type: str  # 'protocol' or 'chain'
    coingecko_id: str
    defillama_slug: Optional[str]
    chain: str
    contract_address: Optional[str]
    value_accrual: str
    notes: str
    # True for tokens with no hard max supply (ETH, SOL). FDV and FDV/MC are
    # reported as N/A rather than silently set to MC (CoinGecko's default).
    uncapped: bool = False


def load_peers(path: Path = ROOT / "peer_set.yaml") -> list[Peer]:
    """Parse peer_set.yaml into a list of Peer dataclasses."""
    with open(path) as f:
        config = yaml.safe_load(f)
    return [Peer(**entry) for entry in config["peers"]]


def get_api_key(name: str) -> Optional[str]:
    """Return an API key from env, or None if blank/unset."""
    val = os.getenv(name, "").strip()
    return val if val else None


# Convenience accessors
def coingecko_key() -> Optional[str]: return get_api_key("COINGECKO_API_KEY")
def coindesk_key() -> Optional[str]: return get_api_key("COINDESK_API_KEY")
def dune_key() -> Optional[str]: return get_api_key("DUNE_API_KEY")

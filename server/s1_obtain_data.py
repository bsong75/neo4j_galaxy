import json
import os
import logging
import uuid
from datetime import datetime, timezone, timedelta

from es_client import get_es_client, PAX_INDEX

logger = logging.getLogger(__name__)

MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'pax_data.json')

FRESHNESS_HOURS = 24


def fetch_pax_data(upid: str) -> dict | None:
    """Fetch passenger data by UPID.

    Checks Elasticsearch first for a fresh cached copy (< 24 hours).
    Falls back to pax_data.json if not found, then ingests into ES.
    """
    logger.info(f"Fetching pax data for UPID: {upid}")

    # 1. Try Elasticsearch first
    try:
        es = get_es_client()
        hit = _search_es(es, upid)
        if hit is not None:
            logger.info(f"Found fresh data in Elasticsearch for UPID: {upid}")
            return hit
    except Exception as e:
        logger.warning(f"Elasticsearch lookup failed, falling back to file: {e}")

    # 2. Fallback to pax_data.json
    raw = _load_from_file(upid)
    if raw is None:
        return None

    # 3. Ingest into ES for next time
    try:
        es = get_es_client()
        _ingest_to_es(es, upid, raw)
    except Exception as e:
        logger.warning(f"Failed to ingest into Elasticsearch: {e}")

    return raw


def _search_es(es, upid: str) -> dict | None:
    """Search ES for a fresh document matching this UPID."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS)).isoformat()

    result = es.search(
        index=PAX_INDEX,
        body={
            'query': {
                'bool': {
                    'must': [
                        {'term': {'UNF_PSNGR_ID': str(upid)}},
                        {'range': {'ingested_ts': {'gte': cutoff}}},
                    ]
                }
            },
            'size': 1,
        },
        ignore=[404],
    )

    hits = result.get('hits', {}).get('hits', [])
    if not hits:
        return None

    source = hits[0]['_source']
    # Remove metadata fields before returning
    source.pop('doc_id', None)
    source.pop('ingested_ts', None)
    return source


def _load_from_file(upid: str) -> dict | None:
    """Load passenger data from the local JSON file."""
    try:
        with open(MOCK_DATA_PATH, 'r') as f:
            mock_data = json.load(f)
    except FileNotFoundError:
        logger.error(f"Mock data file not found: {MOCK_DATA_PATH}")
        return None

    if str(mock_data.get('UNF_PSNGR_ID')) == str(upid):
        return mock_data

    logger.warning(f"No data found for UPID: {upid}")
    return None


def _ingest_to_es(es, upid: str, data: dict) -> None:
    """Index passenger data into Elasticsearch with metadata."""
    doc_id = str(uuid.uuid4())
    doc = {
        **data,
        'doc_id': doc_id,
        'ingested_ts': datetime.now(timezone.utc).isoformat(),
    }

    es.index(index=PAX_INDEX, id=doc_id, body=doc)
    logger.info(f"Ingested UPID {upid} into Elasticsearch (doc_id: {doc_id})")

import json
import os
import logging

logger = logging.getLogger(__name__)

# Path to mock data file
# In Docker: server code is at /app/, data volume mounted at /app/data/
MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'pax_data.json')


def fetch_pax_data(upid: str) -> dict | None:
    """Fetch passenger data by UPID.

    Currently uses mock data from pax_data.json.
    Replace this function body with real Elasticsearch queries later.
    """
    logger.info(f"Fetching pax data for UPID: {upid}")

    try:
        with open(MOCK_DATA_PATH, 'r') as f:
            mock_data = json.load(f)
    except FileNotFoundError:
        logger.error(f"Mock data file not found: {MOCK_DATA_PATH}")
        return None

    # Search through all keys for a matching UPID
    for key, value in mock_data.items():
        if value.get('status') == 'SUCCESS':
            data = value.get('data', {})
            if str(data.get('UNF_PSNGR_ID')) == str(upid):
                return data

    logger.warning(f"No data found for UPID: {upid}")
    return None

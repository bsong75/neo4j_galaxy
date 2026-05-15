import os
import logging
from flask import Blueprint, jsonify
from neo4j_client import get_driver
from es_client import fetch_pax_data
from graph_builder import build_graph_for_pax

logger = logging.getLogger(__name__)

upax_bp = Blueprint('upax', __name__)

REACT_APP_URL = os.environ.get('REACT_APP_URL', 'http://localhost:3005')


@upax_bp.route('/upax_data/<upid>/')
def get_upax_data(upid):
    """Fetch passenger data from ES, build graph, return JSON summary."""

    # 1. Fetch data from Elasticsearch (mock for now)
    pax_data = fetch_pax_data(upid)
    if pax_data is None:
        return jsonify({'status': 'NOT_FOUND', 'message': f'No data found for UPID: {upid}'}), 404

    # 2. Build the Neo4j graph
    try:
        driver = get_driver()
        build_graph_for_pax(driver, pax_data)
    except Exception as e:
        logger.error(f"Graph build failed for UPID {upid}: {e}")
        return jsonify({'status': 'ERROR', 'message': f'Graph build failed: {str(e)}'}), 500

    # 3. Build JSON response for the Angular app
    def _format_derog(d):
        return {
            'type': d.get('DEROG_TYP_CD', ''),
            'source': d.get('DEROG_SRC_CD', ''),
            'description': d.get('DEROG_DESC', ''),
            'date': d.get('DEROG_DT', ''),
            'status': d.get('DEROG_STAT_CD', ''),
            'seizure_ind': d.get('SEIZURE_IND', ''),
            'seizure_items': [
                {
                    'name': item.get('SEIZURE_ITEM_NM', ''),
                    'quantity': item.get('SEIZURE_QTY', ''),
                    'date': item.get('SEIZURE_DT', ''),
                }
                for item in d.get('SEIZURE_ITEMS', [])
            ],
        }

    derog_list = [_format_derog(d) for d in pax_data.get('DEROG', [])]

    def _format_associated_person(rel):
        ap = {
            'first_name': rel.get('GV_NM', ''),
            'last_name': rel.get('LST_NM', ''),
            'relationship_type': rel.get('RLTN_TYP', ''),
            'derog': [_format_derog(d) for d in rel.get('DEROG', [])],
            'associated_persons': [
                _format_associated_person(sub_rel)
                for sub_rel in rel.get('RELATIONSHIPS', [])
            ],
        }
        return ap

    associated_persons = [_format_associated_person(rel) for rel in pax_data.get('RELATIONSHIPS', [])]

    return jsonify({
        'status': 'SUCCESS',
        'person': {
            'id': pax_data.get('UNF_PSNGR_ID', ''),
            'first_name': pax_data.get('FRST_NM', ''),
            'last_name': pax_data.get('LST_NM', ''),
            'dob': pax_data.get('DOB_DT', ''),
            'gender': pax_data.get('GNDR_CD', ''),
            'citizenship_country': pax_data.get('CTZNSHP_CTRY_CD', ''),
        },
        'derog': derog_list,
        'associated_persons': associated_persons,
        'graph_url': f'{REACT_APP_URL}/person/{upid}',
    })

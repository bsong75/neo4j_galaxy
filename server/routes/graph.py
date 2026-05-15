import os
import requests as http_requests
from flask import Blueprint, jsonify, request
from neo4j_client import get_driver

graph_bp = Blueprint('graph', __name__)

NODE_COLORS = {
    'MainPassenger': '#4CAF50',
    'Name': '#FF9800',
    'Phone': '#2196F3',
    'Document': '#795548',
    'Country': '#00BCD4',
    'BirthLocation': '#F44336',
    'Address': '#9C27B0',
    'AssociatedPerson': '#8BC34A',
    'Derog': '#E91E63',
    'SeizureItem': '#607D8B',
}


def node_to_dict(node):
    """Convert a Neo4j node to a dict for react-force-graph."""
    labels = list(node.labels)
    label = labels[0] if labels else 'Unknown'
    props = {}
    for key, val in dict(node).items():
        # Skip internal tracking fields from the response
        if key in ('upid', 'created_at'):
            continue
        if hasattr(val, 'isoformat'):
            props[key] = val.isoformat()
        else:
            props[key] = val
    return {
        'id': node.element_id,
        'label': label,
        'properties': props,
        'color': NODE_COLORS.get(label, '#999999'),
    }


def run_and_collect(session, cypher, **params):
    """Run a Cypher query and convert results to {nodes, links} while session is open."""
    nodes_map = {}
    links = []

    result = session.run(cypher, **params)
    for record in result:
        n = record.get('n')
        r = record.get('r')
        m = record.get('m')

        if n is not None:
            nodes_map[n.element_id] = node_to_dict(n)
        if m is not None:
            nodes_map[m.element_id] = node_to_dict(m)
        if r is not None:
            links.append({
                'source': r.start_node.element_id,
                'target': r.end_node.element_id,
                'type': r.type,
            })

    return {'nodes': list(nodes_map.values()), 'links': links}


def _get_upid():
    """Extract upid from query params. Returns None if not provided."""
    return request.args.get('upid', None)


@graph_bp.route('/graph/full')
def get_full_graph():
    """Get the full graph for a given UPID."""
    upid = _get_upid()
    if not upid:
        return jsonify({'error': 'upid parameter is required'}), 400

    limit = request.args.get('limit', None, type=int)
    driver = get_driver()

    cypher = """
        MATCH (n {upid: $upid})
        OPTIONAL MATCH (n)-[r]->(m {upid: $upid})
        RETURN n, r, m
    """
    params = {'upid': upid}
    if limit:
        cypher += " LIMIT $limit"
        params['limit'] = limit

    with driver.session() as session:
        data = run_and_collect(session, cypher, **params)

    return jsonify(data)


@graph_bp.route('/graph/core')
def get_core_graph():
    """Get MainPassenger, AssociatedPerson, and their Derog nodes for a UPID."""
    upid = _get_upid()
    if not upid:
        return jsonify({'error': 'upid parameter is required'}), 400

    driver = get_driver()

    nodes_map = {}
    links = []

    with driver.session() as session:
        # MainPassenger + AssociatedPerson relationships
        d1 = run_and_collect(session, """
            MATCH (mp:MainPassenger {upid: $upid})
            OPTIONAL MATCH (mp)-[r:ASSOCIATED_WITH]->(ap:AssociatedPerson {upid: $upid})
            RETURN mp AS n, r, ap AS m
        """, upid=upid)
        # MainPassenger derogs
        d2 = run_and_collect(session, """
            MATCH (mp:MainPassenger {upid: $upid})-[r:HAS_DEROG]->(d:Derog {upid: $upid})
            RETURN mp AS n, r, d AS m
        """, upid=upid)
        # AssociatedPerson derogs
        d3 = run_and_collect(session, """
            MATCH (ap:AssociatedPerson {upid: $upid})-[r:HAS_DEROG]->(d:Derog {upid: $upid})
            RETURN ap AS n, r, d AS m
        """, upid=upid)
        # AssociatedPerson -> AssociatedPerson relationships
        d4 = run_and_collect(session, """
            MATCH (ap1:AssociatedPerson {upid: $upid})-[r:ASSOCIATED_WITH]->(ap2:AssociatedPerson {upid: $upid})
            RETURN ap1 AS n, r, ap2 AS m
        """, upid=upid)

    # Merge all results
    for dataset in [d1, d2, d3, d4]:
        for node in dataset['nodes']:
            nodes_map[node['id']] = node
        links.extend(dataset['links'])

    # Deduplicate links
    seen = set()
    unique_links = []
    for link in links:
        key = f"{link['source']}-{link['type']}-{link['target']}"
        if key not in seen:
            seen.add(key)
            unique_links.append(link)

    return jsonify({'nodes': list(nodes_map.values()), 'links': unique_links})


@graph_bp.route('/graph/details')
def get_detail_graph():
    """Get the full graph for a UPID (for expanding from the core view)."""
    upid = _get_upid()
    if not upid:
        return jsonify({'error': 'upid parameter is required'}), 400

    driver = get_driver()

    with driver.session() as session:
        data = run_and_collect(session, """
            MATCH (n {upid: $upid})
            OPTIONAL MATCH (n)-[r]->(m {upid: $upid})
            RETURN n, r, m
        """, upid=upid)

    return jsonify(data)


@graph_bp.route('/graph/person/<person_id>')
def get_person(person_id):
    """Get a MainPassenger and their 1-hop neighbors."""
    upid = _get_upid()
    driver = get_driver()

    params = {'person_id': person_id}
    if upid:
        params['upid'] = upid
        cypher = """
            MATCH (n:MainPassenger {id: $person_id})
            OPTIONAL MATCH (n)-[r]-(m {upid: $upid})
            RETURN n, r, m
        """
    else:
        cypher = """
            MATCH (n:MainPassenger {id: $person_id})
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n, r, m
        """

    with driver.session() as session:
        data = run_and_collect(session, cypher, **params)

    return jsonify(data)


@graph_bp.route('/graph/expand/<path:element_id>')
def expand_node(element_id):
    """Expand a node's neighbors by element ID."""
    upid = _get_upid()
    driver = get_driver()

    params = {'element_id': element_id}
    if upid:
        params['upid'] = upid

    cypher = """
        MATCH (n) WHERE elementId(n) = $element_id
        OPTIONAL MATCH (n)-[r]-(m)
    """
    if upid:
        cypher = """
            MATCH (n) WHERE elementId(n) = $element_id
            OPTIONAL MATCH (n)-[r]-(m {upid: $upid})
        """
    cypher += " RETURN n, r, m"

    with driver.session() as session:
        data = run_and_collect(session, cypher, **params)

    return jsonify(data)


@graph_bp.route('/graph/search')
def search_graph():
    """Search for MainPassenger by id or name within a UPID."""
    q = request.args.get('q', '')
    upid = _get_upid()

    if not q:
        return jsonify({'nodes': [], 'links': []})

    driver = get_driver()
    params = {'q': q}

    if upid:
        params['upid'] = upid
        cypher = """
            MATCH (n:MainPassenger {upid: $upid})
            WHERE n.id CONTAINS $q
               OR n.first_name CONTAINS $q
               OR n.last_name CONTAINS $q
            OPTIONAL MATCH (n)-[r]-(m {upid: $upid})
            RETURN n, r, m
        """
    else:
        cypher = """
            MATCH (n:MainPassenger)
            WHERE n.id CONTAINS $q
               OR n.first_name CONTAINS $q
               OR n.last_name CONTAINS $q
            OPTIONAL MATCH (n)-[r]-(m)
            RETURN n, r, m
        """

    with driver.session() as session:
        data = run_and_collect(session, cypher, **params)

    return jsonify(data)


@graph_bp.route('/graph/filter')
def filter_graph():
    """Filter graph by node types, relationship types for a UPID."""
    upid = _get_upid()
    if not upid:
        return jsonify({'error': 'upid parameter is required'}), 400

    node_types = request.args.get('nodeTypes', '')
    rel_types = request.args.get('relTypes', '')
    limit = request.args.get('limit', None, type=int)

    node_type_list = [t.strip() for t in node_types.split(',') if t.strip()] if node_types else []
    rel_type_list = [t.strip() for t in rel_types.split(',') if t.strip()] if rel_types else []

    driver = get_driver()

    # Build dynamic Cypher based on filters
    where_clauses = ['n.upid = $upid']
    params = {'upid': upid}
    if limit:
        params['limit'] = limit

    if node_type_list:
        label_checks = ' OR '.join([f'"{label}" IN labels(n)' for label in node_type_list])
        where_clauses.append(f'({label_checks})')

    cypher = "MATCH (n)"
    cypher += " WHERE " + " AND ".join(where_clauses)
    cypher += " OPTIONAL MATCH (n)-[r]->(m {upid: $upid})"

    if rel_type_list:
        rel_checks = ' OR '.join([f'type(r) = "{rt}"' for rt in rel_type_list])
        cypher += f" WHERE ({rel_checks})"

    limit_clause = " LIMIT $limit" if limit else ""
    cypher += f" RETURN n, r, m{limit_clause}"

    with driver.session() as session:
        data = run_and_collect(session, cypher, **params)

    return jsonify(data)


@graph_bp.route('/graph/cypher', methods=['POST'])
def run_cypher():
    """Execute a raw Cypher query and return graph results."""
    data = request.get_json()
    cypher = data.get('cypher', '')

    if not cypher:
        return jsonify({'error': 'No cypher provided'}), 400

    # Safety check: block destructive operations
    cypher_upper = cypher.upper()
    if any(word in cypher_upper for word in ['DELETE', 'REMOVE', 'DROP', 'SET ', 'CREATE', 'MERGE']):
        return jsonify({'error': 'Only read operations are allowed.'}), 400

    try:
        driver = get_driver()
        with driver.session() as session:
            graph_data = run_and_collect(session, cypher)
        return jsonify(graph_data)
    except Exception as e:
        return jsonify({'error': f'Cypher error: {str(e)}'}), 400


@graph_bp.route('/graph/summarize', methods=['POST'])
def summarize_graph():
    """Use Groq to generate a natural language summary of the graph data."""
    data = request.get_json()
    nodes = data.get('nodes', [])

    if not nodes:
        return jsonify({'summary': 'No graph data to summarize.'})

    groq_key = os.environ.get('GROQ_API_KEY', '')
    if not groq_key:
        return jsonify({'summary': 'AI summary unavailable (GROQ_API_KEY not set).'})

    # Build compact summary for the LLM
    node_summaries = []
    for node in nodes[:30]:
        props = {k: v for k, v in node.get('properties', {}).items()}
        props['_label'] = node.get('label', 'Unknown')
        node_summaries.append(props)

    prompt = """You are an intelligence analyst assistant. Given graph data about a passenger and their connections, provide a brief executive summary.

Format your response as follows:
1. One opening sentence with the main passenger's name and key identifiers.
2. A bullet point list for derogatory records (derogs), one bullet per derog:
   - Include who has the derog (name), the type, source, and description
   - Include seizure items if any (name, quantity)
3. One closing sentence summarizing associated persons count and relationship types.

Use bullet points (•) for the derog list. Be concise and factual. Do NOT mention graph databases, nodes, or technical terms — write as if briefing an analyst."""

    try:
        resp = http_requests.post(
            'https://api.groq.com/openai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {groq_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile'),
                'messages': [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': f'Graph data ({len(nodes)} items): {node_summaries}'},
                ],
                'temperature': 0,
            },
            timeout=30,
        )
        resp.raise_for_status()
        summary = resp.json()['choices'][0]['message']['content']
        return jsonify({'summary': summary})
    except Exception as e:
        return jsonify({'summary': f'Summary generation failed: {str(e)}'})


@graph_bp.route('/graph/schema')
def get_schema():
    """Return available node labels and relationship types."""
    driver = get_driver()

    with driver.session() as session:
        labels_result = session.run("CALL db.labels()")
        labels = [record['label'] for record in labels_result]

        rel_result = session.run("CALL db.relationshipTypes()")
        rel_types = [record['relationshipType'] for record in rel_result]

    return jsonify({
        'nodeLabels': labels,
        'relationshipTypes': rel_types,
        'nodeColors': NODE_COLORS,
    })

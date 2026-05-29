import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


_indexes_created = False


def ensure_indexes(driver) -> None:
    """Create indexes on frequently queried properties (runs once per process)."""
    global _indexes_created
    if _indexes_created:
        return
    with driver.session() as session:
        session.run("CREATE INDEX IF NOT EXISTS FOR (mp:MainPassenger) ON (mp.upid)").consume()
        session.run("CREATE INDEX IF NOT EXISTS FOR (mp:MainPassenger) ON (mp.id)").consume()
        session.run("CREATE INDEX IF NOT EXISTS FOR (mp:MainPassenger) ON (mp.created_at)").consume()
        session.run("CREATE INDEX IF NOT EXISTS FOR (ap:AssociatedPerson) ON (ap.id)").consume()
    _indexes_created = True
    logger.info("Neo4j indexes ensured")


def graph_is_fresh(driver, upid: str, max_age_hours: int = 24) -> bool:
    """Return True if a graph for this UPID exists and is less than max_age_hours old."""
    ensure_indexes(driver)

    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()

    with driver.session() as session:
        result = session.run("""
            MATCH (mp:MainPassenger {upid: $upid})
            WHERE mp.created_at > $cutoff
            RETURN mp LIMIT 1
        """, upid=upid, cutoff=cutoff)
        return result.single() is not None


def build_graph_for_pax(driver, pax_data: dict) -> None:
    """Delete existing graph for this UPID, then rebuild from data."""

    upid = str(pax_data.get('UNF_PSNGR_ID'))
    logger.info(f"Building graph for UPID: {upid}")

    with driver.session() as session:
        # Delete this UPID's nodes
        session.run("MATCH (n {upid: $upid}) DETACH DELETE n", upid=upid).consume()

        # Also delete old pre-UPID data
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            OPTIONAL MATCH (mp)-[*1..4]-(connected)
            DETACH DELETE connected, mp
        """, upid=upid).consume()

        logger.info(f"Cleared existing nodes for UPID: {upid}")

        now = datetime.now(timezone.utc).isoformat()

        # Build graph: create all nodes and relationships
        _build_main_passenger(session, pax_data, upid, now)
        _build_country(session, pax_data, upid, now)
        _build_birth_locations(session, pax_data, upid, now)
        _build_phones(session, pax_data, upid, now)
        _build_addresses(session, pax_data, upid, now)
        _build_seacats(session, pax_data.get('SEACATS', []), upid, upid, 'MainPassenger', now)
        _build_co_travelers(session, pax_data, upid, now)

        logger.info("Graph build complete")


def cleanup_old_graphs(driver, max_age_hours: int = 24) -> int:
    """Delete all nodes older than max_age_hours. Returns count of deleted nodes."""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).isoformat()

    with driver.session() as session:
        result = session.run("""
            MATCH (n) WHERE n.created_at < $cutoff
            WITH n LIMIT 10000
            DETACH DELETE n
            RETURN count(*) AS deleted
        """, cutoff=cutoff)
        deleted = result.single()['deleted']

    logger.info(f"Cleanup: deleted {deleted} nodes older than {max_age_hours}h")
    return deleted


def _build_main_passenger(session, data, upid, now):
    session.run("""
        CREATE (mp:MainPassenger {
            id: $id,
            upid: $upid,
            created_at: $now,
            first_name: $first_name,
            last_name: $last_name,
            dob: $dob,
            gender: $gender,
            citizenship_country: $citizenship_country,
            icon: '👤'
        })
    """, id=upid, upid=upid, now=now,
         first_name=data.get('FRST_NM', ''),
         last_name=data.get('LST_NM', ''),
         dob=data.get('DOB_DT', ''),
         gender=data.get('GNDR_CD', ''),
         citizenship_country=data.get('CTZNSHP_CTRY_CD', '')).consume()


def _build_country(session, data, upid, now):
    ctry = data.get('CTZNSHP_CTRY_CD')
    if ctry:
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (c:Country {code: $code, upid: $upid, created_at: $now, icon: '🌍'})
            CREATE (mp)-[:FROM_COUNTRY]->(c)
        """, upid=upid, code=ctry, now=now).consume()


def _build_birth_locations(session, data, upid, now):
    for bl in data.get('BIRTH_LOC', []):
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (bl:BirthLocation {country: $country, city: $city, upid: $upid, created_at: $now, icon: '🏠'})
            CREATE (mp)-[:BORN_IN]->(bl)
        """, upid=upid, now=now,
             country=bl.get('BIRTH_CTRY_CD', ''),
             city=bl.get('BIRTH_CITY_NM', '')).consume()


def _build_phones(session, data, upid, now):
    for phone in data.get('PHONE_NUMBERS', []):
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (ph:Phone {number: $number, upid: $upid, created_at: $now, icon: '📱'})
            CREATE (mp)-[:HAS_PHONE]->(ph)
        """, upid=upid, now=now, number=phone.get('PHN_NBR', '')).consume()


def _build_addresses(session, data, upid, now):
    for addr in data.get('ADDRESSES', []):
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (a:Address {address: $address, type: $type, upid: $upid, created_at: $now, icon: '📍'})
            CREATE (mp)-[:HAS_ADDRESS]->(a)
        """, upid=upid, now=now,
             address=addr.get('ADDR', ''),
             type=addr.get('ADDR_TYP', '')).consume()


def _build_seacats(session, seacats, parent_id, upid, parent_label, now):
    """Build Seacat nodes attached to a parent (MainPassenger or AssociatedPerson)."""
    for i, sc in enumerate(seacats):
        seacat_id = f"{parent_id}_seacat_{i}"
        session.run(f"""
            MATCH (p:{parent_label} {{id: $parent_id}})
            CREATE (s:Seacat {{
                id: $seacat_id,
                enf_action_id: $enf_action_id,
                incident_datetime: $incident_datetime,
                incident_id: $incident_id,
                incident_type: $incident_type,
                upid: $upid,
                created_at: $now,
                icon: '\u26A0\uFE0F'
            }})
            CREATE (p)-[:HAS_SEACAT]->(s)
        """, parent_id=parent_id, upid=upid, now=now,
             seacat_id=seacat_id,
             enf_action_id=sc.get('ENF_ACTN_ID', ''),
             incident_datetime=sc.get('NCDNT_DTTM', ''),
             incident_id=sc.get('NCDNT_ID', ''),
             incident_type=sc.get('NCDNT_TYP', '')).consume()


def _build_visa(session, visas, parent_id, upid, parent_label, now):
    """Build Visa nodes attached to a parent (AssociatedPerson)."""
    for i, v in enumerate(visas):
        visa_id = f"{parent_id}_visa_{i}"
        session.run(f"""
            MATCH (p:{parent_label} {{id: $parent_id}})
            CREATE (vi:Visa {{
                id: $visa_id,
                name: 'VISA',
                type: $type,
                refusal_code: $refusal_code,
                refusal_datetime: $refusal_datetime,
                upid: $upid,
                created_at: $now,
                icon: '📋'
            }})
            CREATE (p)-[:HAS_VISA]->(vi)
        """, parent_id=parent_id, upid=upid, now=now,
             visa_id=visa_id,
             type=v.get('TYPE', ''),
             refusal_code=v.get('RFSL_CD', ''),
             refusal_datetime=v.get('RFSL_DTTM', '')).consume()


def _build_secondary(session, secondaries, parent_id, upid, parent_label, now):
    """Build Secondary nodes attached to a parent (AssociatedPerson)."""
    for i, sec in enumerate(secondaries):
        sec_id = f"{parent_id}_secondary_{i}"
        session.run(f"""
            MATCH (p:{parent_label} {{id: $parent_id}})
            CREATE (s:Secondary {{
                id: $sec_id,
                name: 'SECONDARY',
                sub_transaction_type: $sub_trn_type,
                reason: $reason,
                crossing_datetime: $crossing_datetime,
                referral_workspace_id: $referral_id,
                upid: $upid,
                created_at: $now,
                icon: '🔍'
            }})
            CREATE (p)-[:HAS_SECONDARY]->(s)
        """, parent_id=parent_id, upid=upid, now=now,
             sec_id=sec_id,
             sub_trn_type=sec.get('SUB_TRN_TYP', ''),
             reason=sec.get('RSN_TXT', ''),
             crossing_datetime=sec.get('CRSG_DTTM', ''),
             referral_id=str(sec.get('RFRL_WRKSPC_ID_NBR', ''))).consume()


def _build_co_travelers(session, data, upid, now):
    """Build AssociatedPerson nodes from UNF_PRSN_CO_TRAVELERS, with nested CO_TRAVELERS."""
    for i, ct in enumerate(data.get('UNF_PRSN_CO_TRAVELERS', [])):
        ap_id = f"{upid}_ct_{i}"

        # Create AssociatedPerson + relationship to MainPassenger
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (ap:AssociatedPerson {
                id: $ap_id,
                unf_psngr_id: $unf_psngr_id,
                first_name: $first_name,
                last_name: $last_name,
                dob: $dob,
                upid: $upid,
                created_at: $now,
                icon: '👥'
            })
            CREATE (mp)-[:CO_TRAVELER]->(ap)
        """, upid=upid, now=now,
             ap_id=ap_id,
             unf_psngr_id=str(ct.get('UNF_PSNGR_ID', '')),
             first_name=ct.get('FRST_NM', ''),
             last_name=ct.get('LST_NM', ''),
             dob=ct.get('DOB_DT', '')).consume()

        # Seacats for this co-traveler
        _build_seacats(session, ct.get('SEACATS', []), ap_id, upid, 'AssociatedPerson', now)

        # Visa records for this co-traveler
        _build_visa(session, ct.get('VISA', []), ap_id, upid, 'AssociatedPerson', now)

        # Secondary records for this co-traveler
        _build_secondary(session, ct.get('SECONDARY', []), ap_id, upid, 'AssociatedPerson', now)

        # Nested co-travelers (CO_TRAVELERS within a co-traveler)
        for j, sub_ct in enumerate(ct.get('CO_TRAVELERS', [])):
            sub_ap_id = f"{ap_id}_ct_{j}"

            session.run("""
                MATCH (parent_ap:AssociatedPerson {id: $ap_id})
                CREATE (ap:AssociatedPerson {
                    id: $sub_ap_id,
                    unf_psngr_id: $unf_psngr_id,
                    first_name: $first_name,
                    last_name: $last_name,
                    dob: $dob,
                    upid: $upid,
                    created_at: $now,
                    icon: '👥'
                })
                CREATE (parent_ap)-[:CO_TRAVELER]->(ap)
            """, ap_id=ap_id, upid=upid, now=now,
                 sub_ap_id=sub_ap_id,
                 unf_psngr_id=str(sub_ct.get('UNF_PSNGR_ID', '')),
                 first_name=sub_ct.get('FRST_NM', ''),
                 last_name=sub_ct.get('LST_NM', ''),
                 dob=sub_ct.get('DOB_DT', '')).consume()

            # Seacats for nested co-traveler
            _build_seacats(session, sub_ct.get('SEACATS', []), sub_ap_id, upid, 'AssociatedPerson', now)

            # Visa for nested co-traveler
            _build_visa(session, sub_ct.get('VISA', []), sub_ap_id, upid, 'AssociatedPerson', now)

            # Secondary for nested co-traveler
            _build_secondary(session, sub_ct.get('SECONDARY', []), sub_ap_id, upid, 'AssociatedPerson', now)

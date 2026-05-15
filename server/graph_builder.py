import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def build_graph_for_pax(driver, pax_data: dict) -> None:
    """Delete existing graph for this UPID, then rebuild from ES data."""

    upid = str(pax_data.get('UNF_PSNGR_ID'))
    logger.info(f"Building graph for UPID: {upid}")

    with driver.session() as session:
        # Delete this UPID's nodes (new format with upid property)
        session.run("MATCH (n {upid: $upid}) DETACH DELETE n", upid=upid).consume()

        # Also delete old pre-UPID data: any MainPassenger with this id
        # and all nodes connected to it (catches stale nodes without upid property)
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
        _build_document(session, pax_data, upid, now)
        _build_aliases(session, pax_data, upid, now)
        _build_phones(session, pax_data, upid, now)
        _build_addresses(session, pax_data, upid, now)
        _build_associated_persons(session, pax_data, upid, now)
        _build_derogs(session, pax_data, upid, now)

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


def _build_document(session, data, upid, now):
    doc_nbr = data.get('RCNT_DOC_NBR')
    if doc_nbr:
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (d:Document {id_number: $id_number, doc_type: $doc_type, upid: $upid, created_at: $now, icon: '📄'})
            CREATE (mp)-[:HAS_DOC]->(d)
        """, upid=upid, now=now,
             id_number=doc_nbr,
             doc_type=data.get('RCNT_DOC_TYP_CD', '')).consume()


def _build_aliases(session, data, upid, now):
    for name in data.get('NAMES', []):
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (n:Name {first_name: $first_name, last_name: $last_name, upid: $upid, created_at: $now, icon: '🏷️'})
            CREATE (mp)-[:HAS_ALIAS]->(n)
        """, upid=upid, now=now,
             first_name=name.get('FRST_NM', ''),
             last_name=name.get('LST_NM', '')).consume()


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


def _build_associated_persons(session, data, upid, now):
    for rel in data.get('RELATIONSHIPS', []):
        seq = rel.get('RLNTNSHP_INTRNL_SEQ', 0)
        ap_id = f"{upid}_rel_{seq}"

        # Create AssociatedPerson + relationship to MainPassenger
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (ap:AssociatedPerson {
                id: $ap_id,
                first_name: $first_name,
                last_name: $last_name,
                relationship_type: $rel_type,
                upid: $upid,
                created_at: $now,
                icon: '👥'
            })
            CREATE (mp)-[:ASSOCIATED_WITH]->(ap)
        """, upid=upid, now=now,
             ap_id=ap_id,
             first_name=rel.get('GV_NM', ''),
             last_name=rel.get('LST_NM', ''),
             rel_type=rel.get('RLTN_TYP', '')).consume()

        # Phone numbers for this associated person
        for phn in rel.get('PHN_NBR', []):
            session.run("""
                MATCH (ap:AssociatedPerson {id: $ap_id})
                CREATE (ph:Phone {number: $number, upid: $upid, created_at: $now, icon: '📱'})
                CREATE (ap)-[:HAS_PHONE]->(ph)
            """, ap_id=ap_id, number=phn, upid=upid, now=now).consume()

        # Derog records for this associated person
        for derog in rel.get('DEROG', []):
            d_seq = derog.get('DEROG_INTRNL_SEQ', 0)
            derog_id = f"{ap_id}_derog_{d_seq}"

            session.run("""
                MATCH (ap:AssociatedPerson {id: $ap_id})
                CREATE (d:Derog {
                    id: $derog_id,
                    seq: $seq,
                    type: $type,
                    source: $source,
                    description: $description,
                    date: $date,
                    status: $status,
                    seizure_ind: $seizure_ind,
                    upid: $upid,
                    created_at: $now,
                    icon: '\u26A0\uFE0F'
                })
                CREATE (ap)-[:HAS_DEROG]->(d)
            """, ap_id=ap_id, upid=upid, now=now,
                 derog_id=derog_id,
                 seq=d_seq,
                 type=derog.get('DEROG_TYP_CD', ''),
                 source=derog.get('DEROG_SRC_CD', ''),
                 description=derog.get('DEROG_DESC', ''),
                 date=derog.get('DEROG_DT', ''),
                 status=derog.get('DEROG_STAT_CD', ''),
                 seizure_ind=derog.get('SEIZURE_IND', '')).consume()

            for item in derog.get('SEIZURE_ITEMS', []):
                session.run("""
                    MATCH (d:Derog {id: $derog_id})
                    CREATE (si:SeizureItem {
                        name: $name,
                        quantity: $quantity,
                        date: $date,
                        upid: $upid,
                        created_at: $now,
                        icon: '📦'
                    })
                    CREATE (d)-[:SEIZED_ITEM]->(si)
                """, derog_id=derog_id, upid=upid, now=now,
                     name=item.get('SEIZURE_ITEM_NM', ''),
                     quantity=item.get('SEIZURE_QTY', ''),
                     date=item.get('SEIZURE_DT', '')).consume()

        # Nested AssociatedPersons (AP -> AP)
        for sub_rel in rel.get('RELATIONSHIPS', []):
            sub_seq = sub_rel.get('RLNTNSHP_INTRNL_SEQ', 0)
            sub_ap_id = f"{ap_id}_rel_{sub_seq}"

            session.run("""
                MATCH (parent_ap:AssociatedPerson {id: $ap_id})
                CREATE (ap:AssociatedPerson {
                    id: $sub_ap_id,
                    first_name: $first_name,
                    last_name: $last_name,
                    relationship_type: $rel_type,
                    upid: $upid,
                    created_at: $now,
                    icon: '👥'
                })
                CREATE (parent_ap)-[:ASSOCIATED_WITH]->(ap)
            """, ap_id=ap_id, upid=upid, now=now,
                 sub_ap_id=sub_ap_id,
                 first_name=sub_rel.get('GV_NM', ''),
                 last_name=sub_rel.get('LST_NM', ''),
                 rel_type=sub_rel.get('RLTN_TYP', '')).consume()

            # Phones for nested AP
            for phn in sub_rel.get('PHN_NBR', []):
                session.run("""
                    MATCH (ap:AssociatedPerson {id: $sub_ap_id})
                    CREATE (ph:Phone {number: $number, upid: $upid, created_at: $now, icon: '📱'})
                    CREATE (ap)-[:HAS_PHONE]->(ph)
                """, sub_ap_id=sub_ap_id, number=phn, upid=upid, now=now).consume()

            # Derogs for nested AP
            for sub_derog in sub_rel.get('DEROG', []):
                sd_seq = sub_derog.get('DEROG_INTRNL_SEQ', 0)
                sub_derog_id = f"{sub_ap_id}_derog_{sd_seq}"

                session.run("""
                    MATCH (ap:AssociatedPerson {id: $sub_ap_id})
                    CREATE (d:Derog {
                        id: $derog_id,
                        seq: $seq,
                        type: $type,
                        source: $source,
                        description: $description,
                        date: $date,
                        status: $status,
                        seizure_ind: $seizure_ind,
                        upid: $upid,
                        created_at: $now,
                        icon: '\u26A0\uFE0F'
                    })
                    CREATE (ap)-[:HAS_DEROG]->(d)
                """, sub_ap_id=sub_ap_id, upid=upid, now=now,
                     derog_id=sub_derog_id,
                     seq=sd_seq,
                     type=sub_derog.get('DEROG_TYP_CD', ''),
                     source=sub_derog.get('DEROG_SRC_CD', ''),
                     description=sub_derog.get('DEROG_DESC', ''),
                     date=sub_derog.get('DEROG_DT', ''),
                     status=sub_derog.get('DEROG_STAT_CD', ''),
                     seizure_ind=sub_derog.get('SEIZURE_IND', '')).consume()

                for item in sub_derog.get('SEIZURE_ITEMS', []):
                    session.run("""
                        MATCH (d:Derog {id: $derog_id})
                        CREATE (si:SeizureItem {
                            name: $name,
                            quantity: $quantity,
                            date: $date,
                            upid: $upid,
                            created_at: $now,
                            icon: '📦'
                        })
                        CREATE (d)-[:SEIZED_ITEM]->(si)
                    """, derog_id=sub_derog_id, upid=upid, now=now,
                         name=item.get('SEIZURE_ITEM_NM', ''),
                         quantity=item.get('SEIZURE_QTY', ''),
                         date=item.get('SEIZURE_DT', '')).consume()


def _build_derogs(session, data, upid, now):
    for derog in data.get('DEROG', []):
        seq = derog.get('DEROG_INTRNL_SEQ', 0)
        derog_id = f"{upid}_derog_{seq}"

        # Create Derog + relationship to MainPassenger
        session.run("""
            MATCH (mp:MainPassenger {id: $upid})
            CREATE (d:Derog {
                id: $derog_id,
                seq: $seq,
                type: $type,
                source: $source,
                description: $description,
                date: $date,
                status: $status,
                seizure_ind: $seizure_ind,
                upid: $upid,
                created_at: $now,
                icon: '\u26A0\uFE0F'
            })
            CREATE (mp)-[:HAS_DEROG]->(d)
        """, upid=upid, now=now,
             derog_id=derog_id,
             seq=seq,
             type=derog.get('DEROG_TYP_CD', ''),
             source=derog.get('DEROG_SRC_CD', ''),
             description=derog.get('DEROG_DESC', ''),
             date=derog.get('DEROG_DT', ''),
             status=derog.get('DEROG_STAT_CD', ''),
             seizure_ind=derog.get('SEIZURE_IND', '')).consume()

        # Seizure items for this derog
        for item in derog.get('SEIZURE_ITEMS', []):
            session.run("""
                MATCH (d:Derog {id: $derog_id})
                CREATE (si:SeizureItem {
                    name: $name,
                    quantity: $quantity,
                    date: $date,
                    upid: $upid,
                    created_at: $now,
                    icon: '📦'
                })
                CREATE (d)-[:SEIZED_ITEM]->(si)
            """, derog_id=derog_id, upid=upid, now=now,
                 name=item.get('SEIZURE_ITEM_NM', ''),
                 quantity=item.get('SEIZURE_QTY', ''),
                 date=item.get('SEIZURE_DT', '')).consume()

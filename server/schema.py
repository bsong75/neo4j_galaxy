GRAPH_SCHEMA = """
Node types and their properties:
- MainPassenger: id (string, unique), first_name (string), last_name (string), dob (string), gender (string), citizenship_country (string)
- Name: first_name (string), last_name (string)  -- aliases / alternate names
- Phone: number (string, unique)
- Document: id_number (string, unique), doc_type (string, e.g. 'P' for passport)
- Country: code (string, unique)
- BirthLocation: country (string), city (string)
- Address: address (string), type (string, e.g. 'H' for home)
- AssociatedPerson: id (string, unique), first_name (string), last_name (string), relationship_type (string)
- Derog: seq (integer, unique), type (string), source (string), description (string), date (string), status (string), seizure_ind (string)
- SeizureItem: name (string), quantity (string), date (string)

Relationship types:
MainPassenger -> entity:
  MainPassenger -[:FROM_COUNTRY]-> Country
  MainPassenger -[:BORN_IN]-> BirthLocation
  MainPassenger -[:HAS_ALIAS]-> Name
  MainPassenger -[:HAS_PHONE]-> Phone
  MainPassenger -[:HAS_DOC]-> Document
  MainPassenger -[:HAS_ADDRESS]-> Address
  MainPassenger -[:ASSOCIATED_WITH]-> AssociatedPerson
  MainPassenger -[:HAS_DEROG]-> Derog

AssociatedPerson -> entity:
  AssociatedPerson -[:HAS_PHONE]-> Phone
  AssociatedPerson -[:HAS_DEROG]-> Derog
  AssociatedPerson -[:ASSOCIATED_WITH]-> AssociatedPerson

Derog -> entity:
  Derog -[:SEIZED_ITEM]-> SeizureItem
"""

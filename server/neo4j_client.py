from neo4j import GraphDatabase
from graphdatascience import GraphDataScience
import os

NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://neo4j:7687')
NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'password')
AUTH = (NEO4J_USER, NEO4J_PASSWORD)

_driver = None
_gds = None


def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=AUTH)
    return _driver


def get_gds():
    global _gds
    if _gds is None:
        _gds = GraphDataScience(NEO4J_URI, auth=AUTH)
    return _gds

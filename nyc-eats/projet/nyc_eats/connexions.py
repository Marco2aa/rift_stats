"""Connexions aux trois bases du kit, lues dans les variables d'environnement du conteneur python."""
import os

import psycopg
import redis
from pgvector.psycopg import register_vector
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo1:27017/?replicaSet=rs0")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://nyc:nyc@postgres:5432/nyceats")
BASE_MONGO = os.environ.get("BASE_MONGO", "nyceats")


def base_mongo():
    """La base MongoDB de NYC Eats (un seul client, réutilisé : il gère son pool de connexions)."""
    global _client_mongo
    try:
        return _client_mongo[BASE_MONGO]
    except NameError:
        _client_mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        return _client_mongo[BASE_MONGO]


def client_redis():
    """Un client Redis qui renvoie des chaînes (et non des octets)."""
    return redis.from_url(REDIS_URL, decode_responses=True)


def connexion_postgres():
    """Une connexion PostgreSQL qui sait lire et écrire le type vector de pgvector."""
    connexion = psycopg.connect(POSTGRES_DSN, autocommit=True)
    register_vector(connexion)
    return connexion

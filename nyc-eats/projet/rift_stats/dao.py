"""Accès aux bases de Rift Stats, une classe par base.

    PartieDAO        MongoDB     base riftstats, collection parties : une partie par document,
                                 les 10 joueurs imbriqués dans le tableau participants.
    ClassementRedis  Redis       ensemble trié lol:classement (score = LP), un hash lol:joueur:<puuid>
                                 par joueur, et le cache des réponses de l'API (cache-aside).
    ChampionDAO      PostgreSQL  tables lol_champions (avec un vecteur pgvector par champion, pour la
                                 similarité) et lol_objets, chargées depuis Data Dragon.
"""
import json
import os
import re

import psycopg
import redis
from pgvector.psycopg import register_vector
from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongo1:27017/?replicaSet=rs0")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
POSTGRES_DSN = os.environ.get("POSTGRES_DSN", "postgresql://nyc:nyc@postgres:5432/nyceats")
BASE_LOL = os.environ.get("BASE_LOL", "riftstats")

# Le vecteur d'un champion : ses classes (0 ou 1) puis ses notes Data Dragon ramenées entre 0 et 1.
CLASSES = ["Assassin", "Fighter", "Mage", "Marksman", "Support", "Tank"]
CLASSES_FR = {"Assassin": "Assassin", "Fighter": "Combattant", "Mage": "Mage",
              "Marksman": "Tireur", "Support": "Soutien", "Tank": "Tank"}
NOTES = ["attack", "defense", "magic", "difficulty"]
DIMENSION = len(CLASSES) + len(NOTES)

# Tranches de durée de partie, en secondes, pour $bucket
TRANCHES = [0, 1200, 1500, 1800, 2100, 100000]
NOMS_TRANCHES = {0: "< 20 min", 1200: "20-25 min", 1500: "25-30 min", 1800: "30-35 min", 2100: "> 35 min"}

# Les statistiques des champions n'utilisent que les parties des meilleurs joueurs (collecte), pas celles
# des joueurs cherchés dans l'interface (origine "recherche") : sinon un joueur cherché les fausserait.
LADDER = {"origine": {"$ne": "recherche"}}

_client_mongo = None


def base_mongo():
    global _client_mongo
    if _client_mongo is None:
        _client_mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client_mongo[BASE_LOL]


def connexion_postgres():
    connexion = psycopg.connect(POSTGRES_DSN, autocommit=True)
    connexion.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(connexion)
    return connexion


def _victoire(chemin):
    return {"$sum": {"$cond": [chemin, 1, 0]}}


def _taux(victoires="$victoires", parties="$parties"):
    return {"$round": [{"$multiply": [100, {"$divide": [victoires, parties]}]}, 1]}


def _moi(champ, valeur):
    """Le participant de la partie dont `champ` vaut `valeur` (champion ou puuid)."""
    return {"$first": {"$filter": {"input": "$participants", "cond": {"$eq": [f"$$this.{champ}", valeur]}}}}


class PartieDAO:
    def __init__(self):
        self.parties = base_mongo()["parties"]

    def creer_index(self):
        """Index multiclés sur les champs des joueurs imbriqués : profil et fiche champion rapides."""
        self.parties.create_index("participants.puuid")
        self.parties.create_index("participants.champion_id")
        self.parties.create_index([("date", -1)])

    def compter(self, filtre=None):
        return self.parties.count_documents(filtre or {})

    def existe(self, partie_id):
        return self.parties.count_documents({"_id": partie_id}, limit=1) > 0

    def enregistrer(self, partie):
        """Insère ou remplace : relancer la collecte ne crée pas de doublon (même _id)."""
        self.parties.replace_one({"_id": partie["_id"]}, partie, upsert=True)

    def dernier_patch(self):
        partie = self.parties.find_one({}, {"patch": 1}, sort=[("date", -1)])
        return partie["patch"] if partie else None

    # ---- statistiques des champions

    def stats_champions(self, role=None, min_parties=0):
        """Taux de victoire, présence et KDA de chaque champion ($unwind sur les participants)."""
        total = self.compter(LADDER)
        if total == 0:
            return []
        pipeline = [{"$match": LADDER}, {"$unwind": "$participants"}]
        if role:
            pipeline.append({"$match": {"participants.role": role}})
        pipeline += [
            # 1. par champion et par rôle
            {"$group": {
                "_id": {"champion": "$participants.champion_id", "role": "$participants.role"},
                "nom": {"$first": "$participants.champion"},
                "parties": {"$sum": 1},
                "victoires": _victoire("$participants.victoire"),
                "kills": {"$sum": "$participants.kills"},
                "morts": {"$sum": "$participants.morts"},
                "assists": {"$sum": "$participants.assists"},
            }},
            # 2. par champion, en gardant son rôle principal (le plus joué)
            {"$sort": {"parties": -1}},
            {"$group": {
                "_id": "$_id.champion", "nom": {"$first": "$nom"}, "role": {"$first": "$_id.role"},
                "parties": {"$sum": "$parties"}, "victoires": {"$sum": "$victoires"},
                "kills": {"$sum": "$kills"}, "morts": {"$sum": "$morts"}, "assists": {"$sum": "$assists"},
            }},
            {"$match": {"parties": {"$gte": min_parties}}},
            {"$project": {
                "_id": 0, "champion_id": "$_id", "nom": 1, "role": 1, "parties": 1, "victoires": 1,
                "taux_victoire": _taux(),
                "taux_selection": {"$round": [{"$multiply": [100, {"$divide": ["$parties", total]}]}, 1]},
                "kda": {"$round": [{"$divide": [{"$add": ["$kills", "$assists"]}, {"$max": ["$morts", 1]}]}, 2]},
            }},
            {"$sort": {"taux_victoire": -1}},
        ]
        return list(self.parties.aggregate(pipeline))

    def matchups(self, champion_id, min_parties=2):
        """Contre chaque adversaire direct (même rôle, équipe adverse) : taux de victoire du champion."""
        pipeline = [
            {"$match": {"participants.champion_id": champion_id, **LADDER}},
            {"$project": {"moi": _moi("champion_id", champion_id), "participants": 1}},
            {"$unwind": "$participants"},
            {"$match": {"$expr": {"$and": [
                {"$eq": ["$participants.role", "$moi.role"]},
                {"$ne": ["$participants.equipe", "$moi.equipe"]},
                {"$ne": ["$moi.role", "INCONNU"]}]}}},
            {"$group": {"_id": "$participants.champion_id", "nom": {"$first": "$participants.champion"},
                        "parties": {"$sum": 1}, "victoires": _victoire("$moi.victoire")}},
            {"$match": {"parties": {"$gte": min_parties}}},
            {"$project": {"_id": 0, "champion_id": "$_id", "nom": 1, "parties": 1, "victoires": 1,
                          "taux_victoire": _taux()}},
            {"$sort": {"taux_victoire": -1, "parties": -1}},
        ]
        return list(self.parties.aggregate(pipeline))

    def objets(self, champion_id, limite=40):
        """Les objets les plus souvent en fin de partie dans l'inventaire du champion."""
        pipeline = [
            {"$match": {"participants.champion_id": champion_id, **LADDER}},
            {"$unwind": "$participants"},
            {"$match": {"participants.champion_id": champion_id}},
            {"$unwind": "$participants.objets"},
            {"$group": {"_id": "$participants.objets", "parties": {"$sum": 1},
                        "victoires": _victoire("$participants.victoire")}},
            {"$sort": {"parties": -1}},
            {"$limit": limite},
            {"$project": {"_id": 0, "objet_id": "$_id", "parties": 1, "taux_victoire": _taux()}},
        ]
        return list(self.parties.aggregate(pipeline))

    def par_duree(self, champion_id):
        """Taux de victoire du champion par tranche de durée de partie ($bucket)."""
        pipeline = [
            {"$match": {"participants.champion_id": champion_id, **LADDER}},
            {"$unwind": "$participants"},
            {"$match": {"participants.champion_id": champion_id}},
            {"$bucket": {"groupBy": "$duree_s", "boundaries": TRANCHES, "default": "autre",
                         "output": {"parties": {"$sum": 1}, "victoires": _victoire("$participants.victoire")}}},
        ]
        return [{"tranche": NOMS_TRANCHES.get(t["_id"], str(t["_id"])), "parties": t["parties"],
                 "taux_victoire": round(100 * t["victoires"] / t["parties"], 1)}
                for t in self.parties.aggregate(pipeline)]

    # ---- joueurs

    def chercher_joueurs(self, texte, limite=10):
        """Les joueurs dont le Riot ID contient `texte` (sans tenir compte des majuscules)."""
        motif = {"$regex": re.escape(texte), "$options": "i"}
        pipeline = [
            {"$match": {"participants.pseudo": motif}},
            {"$unwind": "$participants"},
            {"$match": {"participants.pseudo": motif}},
            {"$group": {"_id": "$participants.puuid", "pseudo": {"$first": "$participants.pseudo"},
                        "parties": {"$sum": 1}}},
            {"$sort": {"parties": -1}},
            {"$limit": limite},
            {"$project": {"_id": 0, "puuid": "$_id", "pseudo": 1, "parties": 1}},
        ]
        return list(self.parties.aggregate(pipeline))

    def parties_joueur(self, puuid):
        """Les parties d'un joueur, de la plus récente à la plus ancienne, avec sa ligne à lui."""
        pipeline = [
            {"$match": {"participants.puuid": puuid}},
            {"$sort": {"date": -1}},
            {"$project": {"duree_s": 1, "patch": 1, "date": 1, "file": 1, "moi": _moi("puuid", puuid)}},
        ]
        parties = []
        for p in self.parties.aggregate(pipeline):
            moi = p["moi"]
            parties.append({"partie_id": p["_id"], "date": p["date"].isoformat(), "duree_s": p["duree_s"],
                            "patch": p["patch"], "file": p.get("file"),
                            "pseudo": moi["pseudo"], "champion_id": moi["champion_id"],
                            "champion": moi["champion"], "role": moi["role"], "victoire": moi["victoire"],
                            "kills": moi["kills"], "morts": moi["morts"], "assists": moi["assists"],
                            "or": moi.get("or", 0), "degats": moi.get("degats", 0)})
        return parties

    # ---- infrastructure

    def infra(self):
        base = base_mongo()
        statut = base.client.admin.command("replSetGetStatus")
        noeuds = [{"nom": m["name"], "etat": m["stateStr"], "en_ligne": m["health"] == 1} for m in statut["members"]]
        stockage = next(self.parties.aggregate([{"$collStats": {"storageStats": {}}}]))["storageStats"]
        return {"replica_set": statut["set"], "noeuds": noeuds,
                "documents": stockage["count"], "taille_octets": stockage["size"],
                "taille_moyenne_octets": stockage.get("avgObjSize", 0), "stockage_octets": stockage["storageSize"],
                "index": stockage["nindexes"], "taille_index_octets": stockage["totalIndexSize"]}


class ClassementRedis:
    CLE = "lol:classement"

    def __init__(self, duree_cache=60):
        self.r = redis.from_url(REDIS_URL, decode_responses=True)
        self.duree_cache = duree_cache

    def repond(self):
        try:
            return self.r.ping()
        except redis.RedisError:
            return False

    def enregistrer_joueur(self, puuid, pseudo, lp, victoires, defaites):
        tube = self.r.pipeline()
        tube.zadd(self.CLE, {puuid: lp})
        tube.hset(f"lol:joueur:{puuid}", mapping={"pseudo": pseudo, "lp": lp,
                                                  "victoires": victoires, "defaites": defaites})
        tube.execute()

    def nombre(self):
        return self.r.zcard(self.CLE)

    def top(self, nombre=10):
        joueurs = self.r.zrevrange(self.CLE, 0, nombre - 1, withscores=True)
        tube = self.r.pipeline()
        for puuid, _ in joueurs:
            tube.hgetall(f"lol:joueur:{puuid}")
        fiches = tube.execute()
        return [{"rang": rang, "puuid": puuid, "pseudo": fiche.get("pseudo") or "Joueur inconnu", "lp": int(lp),
                 "victoires": int(fiche.get("victoires", 0)), "defaites": int(fiche.get("defaites", 0))}
                for rang, ((puuid, lp), fiche) in enumerate(zip(joueurs, fiches), start=1)]

    def fiche(self, puuid):
        """Rang et LP d'un joueur s'il est dans le classement, sinon None (ZREVRANK)."""
        rang = self.r.zrevrank(self.CLE, puuid)
        if rang is None:
            return None
        fiche = self.r.hgetall(f"lol:joueur:{puuid}")
        return {"rang": rang + 1, "pseudo": fiche.get("pseudo") or None, "lp": int(fiche.get("lp", 0)),
                "victoires": int(fiche.get("victoires", 0)), "defaites": int(fiche.get("defaites", 0))}

    def noter_rang(self, puuid, rang, duree=600):
        """Le rang officiel d'un joueur cherché (League-V4), gardé 10 minutes."""
        self.r.set(f"lol:rang:{puuid}", json.dumps(rang), ex=duree)

    def lire_rang(self, puuid):
        return self.lire(f"lol:rang:{puuid}")

    def oublier(self, cle):
        self.r.delete(cle)

    def vider_classement(self):
        cles = list(self.r.scan_iter("lol:joueur:*")) + [self.CLE]
        self.r.delete(*cles)

    # le cache des réponses
    def lire(self, cle):
        valeur = self.r.get(cle)
        return None if valeur is None else json.loads(valeur)

    def ecrire(self, cle, valeur):
        self.r.set(cle, json.dumps(valeur), ex=self.duree_cache)

    def vider_cache(self):
        cles = list(self.r.scan_iter("lol:cache:*"))
        if cles:
            self.r.delete(*cles)

    def version(self):
        return self.r.get("lol:version")

    def noter_version(self, version):
        self.r.set("lol:version", version)

    def infra(self):
        memoire = self.r.info("memory")
        return {"en_ligne": True, "cles": self.r.dbsize(), "memoire": memoire["used_memory_human"],
                "cles_cache": sum(1 for _ in self.r.scan_iter("lol:cache:*"))}


class ChampionDAO:
    def creer_tables(self):
        with connexion_postgres() as c:
            c.execute(f"""CREATE TABLE IF NOT EXISTS lol_champions (
                champion_id text PRIMARY KEY,   -- identifiant Data Dragon, ex. 'MonkeyKing'
                cle         integer UNIQUE,     -- championId des parties Riot, ex. 62
                nom         text NOT NULL,      -- nom affiché, ex. 'Wukong'
                titre       text,
                classe      text,               -- classe principale, en français
                tags        text[],
                embedding   vector({DIMENSION}))""")
            c.execute("""CREATE TABLE IF NOT EXISTS lol_objets (
                objet_id integer PRIMARY KEY,   -- identifiant des objets dans les parties Riot
                nom      text NOT NULL,
                prix     integer,
                complet  boolean)               -- objet final (ni composant, ni consommable)""")

    def remplacer(self, champions, objets):
        self.creer_tables()
        with connexion_postgres() as c:
            c.execute("TRUNCATE lol_champions, lol_objets")
            with c.cursor() as cur:
                cur.executemany(
                    "INSERT INTO lol_champions VALUES (%(champion_id)s, %(cle)s, %(nom)s, %(titre)s, "
                    "%(classe)s, %(tags)s, %(embedding)s)", champions)
                cur.executemany("INSERT INTO lol_objets VALUES (%(objet_id)s, %(nom)s, %(prix)s, %(complet)s)", objets)

    def compter(self):
        try:
            with connexion_postgres() as c:
                return c.execute("SELECT count(*) FROM lol_champions").fetchone()[0]
        except psycopg.errors.UndefinedTable:
            return 0

    def tous(self):
        with connexion_postgres() as c:
            lignes = c.execute("SELECT champion_id, nom, titre, classe FROM lol_champions ORDER BY nom").fetchall()
        return [{"champion_id": i, "nom": n, "titre": t, "classe": k} for i, n, t, k in lignes]

    def par_cle(self):
        """{championId Riot: (champion_id, nom)}, pour traduire les parties à la collecte."""
        with connexion_postgres() as c:
            return {cle: (i, n) for cle, i, n in c.execute("SELECT cle, champion_id, nom FROM lol_champions")}

    def objets_complets(self):
        """{objet_id: (nom, prix)} des objets finaux."""
        try:
            with connexion_postgres() as c:
                return {i: (n, p) for i, n, p in c.execute("SELECT objet_id, nom, prix FROM lol_objets WHERE complet")}
        except psycopg.errors.UndefinedTable:
            return {}

    def similaires(self, champion_id, nombre=5):
        """Les champions les plus proches (distance euclidienne <-> de pgvector)."""
        with connexion_postgres() as c:
            lignes = c.execute(
                """SELECT autre.champion_id, autre.nom, round((autre.embedding <-> ref.embedding)::numeric, 3)
                   FROM lol_champions ref JOIN lol_champions autre ON autre.champion_id <> ref.champion_id
                   WHERE ref.champion_id = %s
                   ORDER BY autre.embedding <-> ref.embedding LIMIT %s""", (champion_id, nombre)).fetchall()
        return [{"champion_id": i, "nom": n, "distance": float(d)} for i, n, d in lignes]

    def infra(self):
        with connexion_postgres() as c:
            taille = c.execute("SELECT pg_size_pretty(pg_total_relation_size('lol_champions') "
                               "+ pg_total_relation_size('lol_objets'))").fetchone()[0]
            objets = c.execute("SELECT count(*) FROM lol_objets").fetchone()[0]
        return {"en_ligne": True, "champions": self.compter(), "objets": objets, "taille": taille}

"""Accès aux données de NYC Eats : une classe par base (patron DAO).

Le reste du programme (l'API, le tableau de bord) ne voit jamais une requête MongoDB, une commande
Redis ou du SQL : il appelle ces méthodes. Changer de base ne touche que ce fichier.
"""
import json

from .connexions import base_mongo, client_redis, connexion_postgres


class RestaurantDAO:
    """Les fiches des restaurants, dans MongoDB (collection restaurants)."""

    def __init__(self):
        self.collection = base_mongo()["restaurants"]

    def trouver(self, restaurant_id):
        return self.collection.find_one({"restaurant_id": restaurant_id}, {"_id": 0})

    def rechercher(self, quartier=None, cuisine=None, limite=20):
        filtre = {}
        if quartier:
            filtre["borough"] = quartier
        if cuisine:
            filtre["cuisine"] = cuisine
        projection = {"_id": 0, "restaurant_id": 1, "name": 1, "borough": 1, "cuisine": 1}
        return list(self.collection.find(filtre, projection).sort("name", 1).limit(limite))

    def compter(self, quartier=None):
        return self.collection.count_documents({"borough": quartier} if quartier else {})

    def quartiers(self):
        return sorted(q for q in self.collection.distinct("borough") if q != "Missing")

    def score_moyen_par_cuisine(self, quartier=None, minimum=100, limite=10):
        """Les cuisines les mieux notées aux inspections. Attention : un score BAS est un BON score."""
        etapes = []
        if quartier:
            etapes.append({"$match": {"borough": quartier}})
        etapes += [
            {"$unwind": "$grades"},
            {"$group": {"_id": "$cuisine", "score_moyen": {"$avg": "$grades.score"}, "inspections": {"$sum": 1}}},
            {"$match": {"inspections": {"$gte": minimum}}},
            {"$sort": {"score_moyen": 1}},
            {"$limit": limite},
            {"$project": {"_id": 0, "cuisine": "$_id", "score_moyen": {"$round": ["$score_moyen", 2]}, "inspections": 1}},
        ]
        return list(self.collection.aggregate(etapes))


class CacheRedis:
    """Le cache et les compteurs de consultation, dans Redis."""

    def __init__(self, duree_cache=60):
        self.redis = client_redis()
        self.duree_cache = duree_cache   # secondes

    def lire(self, cle):
        valeur = self.redis.get(cle)
        return json.loads(valeur) if valeur is not None else None

    def ecrire(self, cle, valeur):
        self.redis.set(cle, json.dumps(valeur, default=str), ex=self.duree_cache)

    def compter_vue(self, restaurant_id):
        self.redis.zincrby("classement:vues", 1, restaurant_id)
        return int(self.redis.incr("resto:%s:vues" % restaurant_id))

    def repond(self):
        return self.redis.ping()

    def les_plus_vus(self, nombre=10):
        return [{"restaurant_id": rid, "vues": int(vues)}
                for rid, vues in self.redis.zrevrange("classement:vues", 0, nombre - 1, withscores=True)]


class AvisDAO:
    """Les avis clients (JSONB) et la recherche par le sens (pgvector), dans PostgreSQL."""

    def __init__(self):
        self.connexion = connexion_postgres()

    def compter(self):
        return self.connexion.execute("SELECT count(*) FROM avis").fetchone()[0]

    def avis_du_restaurant(self, restaurant_id, limite=5):
        lignes = self.connexion.execute(
            """SELECT note, publie_le, contenu->>'auteur', contenu->>'texte'
               FROM avis WHERE restaurant_id = %s ORDER BY publie_le DESC LIMIT %s""",
            (restaurant_id, limite)).fetchall()
        return [{"note": n, "date": d, "auteur": a, "texte": t} for n, d, a, t in lignes]

    def note_moyenne_par_quartier(self):
        lignes = self.connexion.execute(
            """SELECT r.quartier, round(avg(a.note), 2), count(*)
               FROM avis a JOIN restaurants r USING (restaurant_id)
               GROUP BY r.quartier ORDER BY r.quartier""").fetchall()
        return [{"quartier": q, "note_moyenne": float(m), "avis": n} for q, m, n in lignes]

    def similaires(self, restaurant_id, nombre=5):
        """Les restaurants dont les avis ressemblent le plus (distance cosinus entre profils).
        Le vecteur cible est lu par une sous-requête : un index HNSW sur profil peut alors servir."""
        lignes = self.connexion.execute(
            """SELECT restaurant_id, nom, cuisine,
                      round((profil <=> (SELECT profil FROM restaurants WHERE restaurant_id = %s))::numeric, 3)
               FROM restaurants
               WHERE restaurant_id <> %s
               ORDER BY profil <=> (SELECT profil FROM restaurants WHERE restaurant_id = %s)
               LIMIT %s""",
            (restaurant_id, restaurant_id, restaurant_id, nombre)).fetchall()
        return [{"restaurant_id": i, "nom": n, "cuisine": c, "distance": float(d)} for i, n, c, d in lignes]

    def requetes_types(self):
        return [{"id": i, "texte": t} for i, t in self.connexion.execute("SELECT id, texte FROM requetes ORDER BY id")]

    def recherche_par_sens(self, requete_id, nombre=5):
        """Les avis les plus proches d'une recherche type (son vecteur est déjà calculé).
        Le vecteur de la requête est lu par une sous-requête : un index HNSW sur embedding peut servir."""
        lignes = self.connexion.execute(
            """SELECT r.nom, a.note, a.contenu->>'texte',
                      round((a.embedding <=> (SELECT embedding FROM requetes WHERE id = %s))::numeric, 3)
               FROM avis a JOIN restaurants r USING (restaurant_id)
               ORDER BY a.embedding <=> (SELECT embedding FROM requetes WHERE id = %s)
               LIMIT %s""",
            (requete_id, requete_id, nombre)).fetchall()
        return [{"restaurant": n, "note": note, "texte": t, "distance": float(d)} for n, note, t, d in lignes]

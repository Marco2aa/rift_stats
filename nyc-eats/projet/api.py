"""API de NYC Eats (FastAPI). Elle ne parle aux bases qu'à travers les classes DAO.

Lancer (depuis la machine, le profil « tous » démarré) :
    docker exec -it python uvicorn api:app --app-dir /projet --host 0.0.0.0 --port 8000 --reload --reload-dir /projet
Documentation interactive : http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException

from nyc_eats.dao import AvisDAO, CacheRedis, RestaurantDAO
from rift_stats.routes import router as routes_lol

app = FastAPI(title="NYC Eats", description="Guide des restaurants de New York : MongoDB + Redis + PostgreSQL")
app.include_router(routes_lol)   # les routes /lol de Rift Stats (League of Legends)
restaurants = RestaurantDAO()
cache = CacheRedis(duree_cache=60)
avis = AvisDAO()


@app.get("/sante")
def sante():
    """Vérifie que les trois bases répondent."""
    return {
        "mongodb": restaurants.compter(),
        "redis": cache.repond(),
        "postgresql": avis.compter(),
    }


@app.get("/quartiers")
def liste_quartiers():
    return restaurants.quartiers()


@app.get("/restaurants")
def rechercher(quartier: str | None = None, cuisine: str | None = None, limite: int = 20):
    return restaurants.rechercher(quartier, cuisine, limite)


@app.get("/restaurants/{restaurant_id}")
def fiche(restaurant_id: str):
    """La fiche d'un restaurant : d'abord le cache Redis, sinon MongoDB (cache-aside)."""
    cle = "cache:resto:%s" % restaurant_id
    resto = cache.lire(cle)
    origine = "cache"
    if resto is None:
        resto = restaurants.trouver(restaurant_id)
        if resto is None:
            raise HTTPException(status_code=404, detail="Restaurant inconnu")
        cache.ecrire(cle, resto)
        origine = "mongodb"
    vues = cache.compter_vue(restaurant_id)
    return {"origine": origine, "vues": vues, "restaurant": resto, "avis": avis.avis_du_restaurant(restaurant_id)}


@app.get("/restaurants/{restaurant_id}/similaires")
def similaires(restaurant_id: str, nombre: int = 5):
    return avis.similaires(restaurant_id, nombre)


@app.get("/stats/cuisines")
def meilleures_cuisines(quartier: str | None = None):
    """Les cuisines au meilleur score d'inspection (score moyen le plus bas)."""
    cle = "cache:stats:cuisines:%s" % (quartier or "tous")
    resultat = cache.lire(cle)
    if resultat is None:
        resultat = restaurants.score_moyen_par_cuisine(quartier)
        cache.ecrire(cle, resultat)
    return resultat


@app.get("/stats/notes")
def notes_par_quartier():
    return avis.note_moyenne_par_quartier()


@app.get("/classement")
def les_plus_vus(nombre: int = 10):
    classement = cache.les_plus_vus(nombre)
    for ligne in classement:
        fiche_resto = restaurants.trouver(ligne["restaurant_id"]) or {}
        ligne["nom"] = fiche_resto.get("name", "?")
    return classement


@app.get("/recherche")
def recherche_par_sens(requete_id: int, nombre: int = 5):
    return avis.recherche_par_sens(requete_id, nombre)


@app.get("/recherche/requetes")
def requetes_types():
    return avis.requetes_types()

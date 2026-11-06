"""Les routes /lol de l'API. Elles n'appellent que les classes DAO de rift_stats.dao."""
from collections import Counter

from fastapi import APIRouter, HTTPException

from rift_stats.dao import ChampionDAO, ClassementRedis, PartieDAO
from rift_stats.riot import REGIONS, Riot, RiotErreur, importer_joueur

router = APIRouter(prefix="/lol", tags=["Rift Stats (League of Legends)"])
parties = PartieDAO()
classement = ClassementRedis(duree_cache=60)
champions = ChampionDAO()


def en_cache(cle, calcul):
    """Cache-aside : la réponse est lue dans Redis, sinon calculée puis gardée 60 s."""
    resultat = classement.lire(cle)
    if resultat is None:
        resultat = calcul()
        classement.ecrire(cle, resultat)
    return resultat


@router.get("/sante")
def sante():
    return {
        "parties": parties.compter(),
        "redis": classement.repond(),
        "champions": champions.compter(),
        "joueurs": classement.nombre(),
        "patch": parties.dernier_patch() or classement.version() or "?",
    }


@router.get("/champions")
def liste_champions():
    return champions.tous()


@router.get("/champions/stats")
def stats_champions(role: str | None = None, min_parties: int = 0):
    """Agrégation MongoDB, complétée par la classe du champion (PostgreSQL)."""
    def calcul():
        resultat = parties.stats_champions(role, min_parties)
        classes = {c["champion_id"]: c["classe"] for c in champions.tous()}
        for ligne in resultat:
            ligne["classe"] = classes.get(ligne["champion_id"], "?")
        return resultat
    return en_cache(f"lol:cache:stats:{role or 'tous'}:{min_parties}", calcul)


@router.get("/champions/{champion_id}/similaires")
def similaires(champion_id: str, nombre: int = 5):
    resultat = champions.similaires(champion_id, nombre)
    if not resultat:
        raise HTTPException(status_code=404, detail="Champion inconnu")
    return resultat


@router.get("/champions/{champion_id}/details")
def details_champion(champion_id: str, min_matchup: int = 2):
    """Matchups, objets clés et taux de victoire selon la durée de la partie."""
    def calcul():
        complets = champions.objets_complets()
        joues = sum(t["parties"] for t in parties.par_duree(champion_id))
        objets = []
        for o in parties.objets(champion_id):
            if o["objet_id"] in complets and len(objets) < 6:
                nom, prix = complets[o["objet_id"]]
                objets.append({**o, "nom": nom, "prix": prix,
                               "frequence": round(100 * o["parties"] / joues, 1) if joues else 0})
        matchups = parties.matchups(champion_id, min_matchup)
        return {"parties": joues, "objets": objets, "duree": parties.par_duree(champion_id),
                "meilleurs_matchups": matchups[:5],
                "pires_matchups": sorted(matchups, key=lambda m: (m["taux_victoire"], -m["parties"]))[:5]}
    return en_cache(f"lol:cache:details:{champion_id}:{min_matchup}", calcul)


@router.get("/classement")
def top_joueurs(nombre: int = 10):
    return classement.top(nombre)


@router.get("/joueurs")
def chercher_joueurs(q: str, limite: int = 10):
    if len(q.strip()) < 2:
        return []
    return parties.chercher_joueurs(q.strip(), limite)


@router.get("/joueurs/{puuid}")
def profil_joueur(puuid: str):
    """Profil d'un joueur : son rang (Redis) et ses parties (MongoDB)."""
    def calcul():
        historique = parties.parties_joueur(puuid)
        fiche = classement.fiche(puuid)
        rang_riot = classement.lire_rang(puuid)
        if not historique and fiche is None and rang_riot is None:
            return None
        n = len(historique)
        victoires = sum(p["victoire"] for p in historique)
        kills, morts, assists = (sum(p[c] for p in historique) for c in ("kills", "morts", "assists"))
        par_champion = Counter(p["champion_id"] for p in historique)
        favoris = []
        for champion_id, nb in par_champion.most_common(5):
            siennes = [p for p in historique if p["champion_id"] == champion_id]
            favoris.append({"champion_id": champion_id, "nom": siennes[0]["champion"], "parties": nb,
                            "taux_victoire": round(100 * sum(p["victoire"] for p in siennes) / nb, 1)})
        roles = Counter(p["role"] for p in historique)
        return {
            "puuid": puuid,
            "pseudo": (fiche or {}).get("pseudo") or (historique[0]["pseudo"] if historique else "Joueur inconnu"),
            "classement": fiche, "rang_riot": rang_riot, "parties": n, "victoires": victoires,
            "taux_victoire": round(100 * victoires / n, 1) if n else None,
            "kda": round((kills + assists) / max(morts, 1), 2) if n else None,
            "role_principal": roles.most_common(1)[0][0] if roles else None,
            "favoris": favoris, "historique": historique[:20],
        }
    resultat = en_cache(f"lol:cache:joueur:{puuid}", calcul)
    if resultat is None:
        raise HTTPException(status_code=404, detail="Joueur inconnu")
    return resultat


@router.post("/riot/joueur")
def importer_depuis_riot(riot_id: str, plateforme: str = "euw1", nombre: int = 15):
    """Va chercher un joueur sur les serveurs Riot (compte, rang, dernières parties) et le range en base.

    POST et non GET : la route écrit dans MongoDB et consomme le quota de la clé Riot (environ nombre + 3 appels).
    Ces parties sont marquées origine "recherche" : elles alimentent le profil, pas les statistiques des champions.
    """
    if plateforme not in REGIONS:
        raise HTTPException(status_code=400, detail="Serveur inconnu")
    try:
        riot = Riot(pause=0.06)   # environ 16 appels par seconde, sous la limite de 20
        resultat = importer_joueur(riot, parties, champions.par_cle(), riot_id, plateforme, min(nombre, 20))
    except RiotErreur as erreur:
        detail = "Riot ID introuvable sur ce serveur" if erreur.statut == 404 else str(erreur)
        raise HTTPException(status_code=erreur.statut, detail=detail)
    if resultat["rang"]:
        classement.noter_rang(resultat["puuid"], resultat["rang"])
    classement.oublier(f"lol:cache:joueur:{resultat['puuid']}")   # le profil en cache est périmé
    resultat["appels_riot"] = riot.appels
    return resultat


@router.get("/infra")
def infra():
    """L'état des trois bases, sans cache : c'est ce qu'on veut voir en direct (panne d'un nœud...)."""
    etat = {}
    for nom, lecture in (("mongodb", parties.infra), ("redis", classement.infra), ("postgresql", champions.infra)):
        try:
            etat[nom] = lecture()
        except Exception as erreur:   # une base en panne ne doit pas faire tomber la route
            etat[nom] = {"en_ligne": False, "erreur": str(erreur)[:200]}
    return etat

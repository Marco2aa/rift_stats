"""Client de l'API Riot, partagé par le script de collecte (travail/lol/collecte_riot.py) et par l'API.

La clé est lue dans la variable d'environnement RIOT_API_KEY (fichier riot.env passé avec --env-file).
"""
import os
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests

# Chaque serveur de jeu (plateforme) dépend d'une région pour les routes Account-V1 et Match-V5
REGIONS = {"euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe", "me1": "europe",
           "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
           "kr": "asia", "jp1": "asia", "oc1": "sea", "sg2": "sea", "tw2": "sea", "vn2": "sea"}
FILE_SOLO = 420          # file classée solo/duo
DUREE_MIN = 300          # moins de 5 minutes : partie annulée (« remake »), on l'ignore


class RiotErreur(Exception):
    def __init__(self, statut, message):
        super().__init__(message)
        self.statut = statut


class Riot:
    def __init__(self, cle=None, pause=1.25):
        cle = cle or os.environ.get("RIOT_API_KEY")
        if not cle:
            raise RiotErreur(503, "Clé Riot absente : lancez l'API avec --env-file riot.env")
        self.session = requests.Session()
        self.session.headers["X-Riot-Token"] = cle
        self.pause = pause
        self.appels = 0

    def get(self, url, **parametres):
        for _ in range(6):
            reponse = self.session.get(url, params=parametres, timeout=15)
            self.appels += 1
            time.sleep(self.pause)
            if reponse.status_code == 429:                      # limite atteinte : Riot dit combien attendre
                attente = int(reponse.headers.get("Retry-After", 10))
                print(f"  limite Riot atteinte, pause de {attente} s")
                time.sleep(attente)
                continue
            if reponse.status_code == 404:
                raise RiotErreur(404, "Introuvable chez Riot")
            if reponse.status_code in (401, 403):
                raise RiotErreur(reponse.status_code, f"Clé Riot refusée (HTTP {reponse.status_code}) : la clé de "
                                 "développement expire au bout de 24 h, régénérez-la sur https://developer.riotgames.com")
            if reponse.status_code >= 500:
                time.sleep(3)
                continue
            reponse.raise_for_status()
            return reponse.json()
        raise RiotErreur(503, f"Riot ne répond pas : {url}")


def alleger(partie, champions, origine):
    """Garde ce qui sert aux statistiques : une partie Riot fait plus de 1 000 champs.

    origine : "ladder" (collecte des meilleurs joueurs) ou "recherche" (un joueur cherché dans l'interface).
    Les statistiques des champions n'utilisent que les parties "ladder".
    """
    info = partie["info"]
    joueurs = []
    for p in info["participants"]:
        champion_id, nom = champions.get(p["championId"], (p["championName"], p["championName"]))
        joueurs.append({
            "puuid": p["puuid"],
            "pseudo": f"{p.get('riotIdGameName', '?')}#{p.get('riotIdTagline', '')}",
            "champion_id": champion_id, "champion": nom,
            "role": p.get("teamPosition") or "INCONNU",
            "equipe": p["teamId"], "victoire": p["win"],
            "kills": p["kills"], "morts": p["deaths"], "assists": p["assists"],
            "or": p["goldEarned"], "degats": p["totalDamageDealtToChampions"],
            "objets": [p[f"item{i}"] for i in range(7) if p.get(f"item{i}")],
        })
    return {
        "_id": partie["metadata"]["matchId"],
        "date": datetime.fromtimestamp(info["gameCreation"] / 1000, tz=timezone.utc),
        "duree_s": info["gameDuration"],
        "patch": ".".join(info["gameVersion"].split(".")[:2]),
        "file": info["queueId"],
        "origine": origine,
        "participants": joueurs,
    }


def importer_joueur(riot, parties, champions, riot_id, plateforme="euw1", nombre=15):
    """Cherche un joueur par Riot ID (Pseudo#TAG), son rang et ses dernières parties, et les range dans MongoDB.

    Les parties déjà en base ne sont pas retéléchargées. Sans partie classée, on prend ses dernières parties
    tous modes confondus (normale, ARAM...).
    """
    if "#" not in riot_id:
        raise RiotErreur(400, "Un Riot ID s'écrit Pseudo#TAG")
    nom, tag = (morceau.strip() for morceau in riot_id.rsplit("#", 1))
    region = REGIONS.get(plateforme, "europe")
    compte = riot.get(f"https://{region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
                      f"{quote(nom)}/{quote(tag)}")
    puuid = compte["puuid"]
    entrees = riot.get(f"https://{plateforme}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}")
    solo = next((x for x in entrees if x["queueType"] == "RANKED_SOLO_5x5"), None)

    liste = f"https://{region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    ids = riot.get(liste, type="ranked", count=nombre) or riot.get(liste, count=nombre)
    nouvelles = 0
    for partie_id in ids:
        if parties.existe(partie_id):
            continue
        partie = riot.get(f"https://{region}.api.riotgames.com/lol/match/v5/matches/{partie_id}")
        if partie["info"]["gameDuration"] >= DUREE_MIN:
            parties.enregistrer(alleger(partie, champions, "recherche"))
            nouvelles += 1
    rang = None
    if solo:
        rang = {"palier": solo["tier"], "division": solo["rank"], "lp": solo["leaguePoints"],
                "victoires": solo["wins"], "defaites": solo["losses"]}
    return {"puuid": puuid, "pseudo": f"{compte.get('gameName', nom)}#{compte.get('tagLine', tag)}",
            "rang": rang, "parties_trouvees": len(ids), "nouvelles": nouvelles}

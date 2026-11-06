"""Charge les champions et les objets de League of Legends depuis Data Dragon (sans clé) dans PostgreSQL.

Lancer :
    docker exec python python /travail/lol/charger_champions.py

Chaque champion reçoit un vecteur (pgvector) : ses classes en 0/1 (Assassin, Fighter, Mage,
Marksman, Support, Tank), puis ses notes attaque, défense, magie et difficulté divisées par 10.
Deux champions proches ont des vecteurs proches : c'est ce qu'utilise la route /lol/champions/{id}/similaires.

Un objet est « complet » s'il est vendu en boutique sur la Faille (carte 11), coûte au moins 900 pièces,
ne se transforme pas en un autre objet et n'est ni consommable ni balise : ce sont les objets finaux.
"""
import sys

import numpy as np
import requests

sys.path.insert(0, "/projet")
from rift_stats.dao import CLASSES, CLASSES_FR, NOTES, ChampionDAO, ClassementRedis, PartieDAO  # noqa: E402

DDRAGON = "https://ddragon.leagueoflegends.com"

version = requests.get(f"{DDRAGON}/api/versions.json", timeout=10).json()[0]
donnees = requests.get(f"{DDRAGON}/cdn/{version}/data/fr_FR/champion.json", timeout=20).json()["data"]
boutique = requests.get(f"{DDRAGON}/cdn/{version}/data/fr_FR/item.json", timeout=20).json()["data"]

champions = []
for champion_id, fiche in donnees.items():
    tags = fiche["tags"]
    vecteur = [1.0 if classe in tags else 0.0 for classe in CLASSES] + [fiche["info"][n] / 10 for n in NOTES]
    champions.append({
        "champion_id": champion_id, "cle": int(fiche["key"]), "nom": fiche["name"], "titre": fiche["title"],
        "classe": CLASSES_FR.get(tags[0], tags[0]) if tags else "?", "tags": tags,
        "embedding": np.array(vecteur, dtype=np.float32),
    })

objets = []
for objet_id, o in boutique.items():
    prix = o["gold"]["total"]
    complet = (o["gold"].get("purchasable", False) and o.get("maps", {}).get("11", False) and prix >= 900
               and not o.get("into") and not o.get("requiredAlly")
               and not {"Consumable", "Trinket"} & set(o.get("tags", [])))
    objets.append({"objet_id": int(objet_id), "nom": o["name"], "prix": prix, "complet": bool(complet)})

ChampionDAO().remplacer(champions, objets)
PartieDAO().creer_index()
cache = ClassementRedis()
cache.noter_version(version)
cache.vider_cache()
print(f"Data Dragon {version} : {len(champions)} champions et {len(objets)} objets "
      f"({sum(o['complet'] for o in objets)} complets) chargés dans PostgreSQL.")

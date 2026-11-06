"""Collecte des parties classées solo/duo des meilleurs joueurs avec l'API Riot, vers MongoDB et Redis.

Il faut une clé (gratuite, valable 24 h) : https://developer.riotgames.com, bouton « Regenerate API Key ».
La clé se passe dans la commande, ou par le fichier riot.env à la racine du kit (hors projet/ et
travail/, à ne pas rendre), depuis le dossier nyc-eats :

    docker exec --env-file riot.env python python -u /travail/lol/collecte_riot.py
    docker exec -it -e RIOT_API_KEY=RGAPI-xxxxxxxx python python /travail/lol/collecte_riot.py

Options : --joueurs 30 (joueurs suivis), --par-joueur 20 (parties par joueur), --parties 600 (maximum),
          --ligue challenger|grandmaster|master, --plateforme euw1.
Lancer d'abord charger_champions.py (pour traduire les championId en noms).

Étapes :
  1. le classement de la ligue (League-V4)          -> Redis : ensemble trié lol:classement (score = LP)
  2. le Riot ID des meilleurs joueurs (Account-V1)  -> Redis : hash lol:joueur:<puuid>
  3. leurs dernières parties (Match-V5), allégées   -> MongoDB : riftstats.parties, une partie par document
La clé de développement permet 100 requêtes toutes les 2 minutes : le script attend 1,25 s entre deux
appels, soit environ 600 parties en 13 minutes. Relancer le script ne crée pas de doublon (_id = matchId).
Le client Riot et la fonction alleger() sont dans /projet/rift_stats/riot.py (partagés avec l'API).
"""
import argparse
import sys

sys.path.insert(0, "/projet")
from rift_stats.dao import ChampionDAO, ClassementRedis, PartieDAO  # noqa: E402
from rift_stats.riot import DUREE_MIN, FILE_SOLO, REGIONS, Riot, RiotErreur, alleger  # noqa: E402


def collecter(args):
    champions = ChampionDAO().par_cle()
    if not champions:
        sys.exit("Aucun champion en base : lancez d'abord /travail/lol/charger_champions.py")

    riot = Riot()
    plateforme = f"https://{args.plateforme}.api.riotgames.com"
    region = f"https://{REGIONS[args.plateforme]}.api.riotgames.com"
    parties, classement = PartieDAO(), ClassementRedis()
    parties.creer_index()

    # 1. le classement de la ligue
    ligue = riot.get(f"{plateforme}/lol/league/v4/{args.ligue}leagues/by-queue/RANKED_SOLO_5x5")
    entrees = sorted((e for e in ligue["entries"] if e.get("puuid")), key=lambda e: e["leaguePoints"], reverse=True)
    print(f"1. Ligue {args.ligue} ({args.plateforme}) : {len(entrees)} joueurs")
    classement.vider_classement()
    for e in entrees:
        classement.enregistrer_joueur(e["puuid"], "", e["leaguePoints"], e["wins"], e["losses"])

    # 2. le Riot ID des meilleurs joueurs, et la liste de leurs parties
    ids_parties = []
    for numero, e in enumerate(entrees[:args.joueurs], start=1):
        compte = riot.get(f"{region}/riot/account/v1/accounts/by-puuid/{e['puuid']}")
        pseudo = f"{compte.get('gameName', '?')}#{compte.get('tagLine', '')}"
        classement.enregistrer_joueur(e["puuid"], pseudo, e["leaguePoints"], e["wins"], e["losses"])
        ids = riot.get(f"{region}/lol/match/v5/matches/by-puuid/{e['puuid']}/ids",
                       queue=FILE_SOLO, type="ranked", count=args.par_joueur)
        ids_parties += [i for i in ids if i not in ids_parties]
        print(f"2. joueur {numero}/{args.joueurs} : {pseudo}, {e['leaguePoints']} LP ({len(ids_parties)} parties repérées)")

    # 3. le détail des parties, allégé, dans MongoDB
    nouvelles = [i for i in ids_parties if not parties.existe(i)][:args.parties]
    print(f"3. {len(nouvelles)} parties à télécharger (les autres sont déjà en base)")
    gardees = 0
    for numero, partie_id in enumerate(nouvelles, start=1):
        partie = riot.get(f"{region}/lol/match/v5/matches/{partie_id}")
        if partie["info"]["gameDuration"] >= DUREE_MIN:
            parties.enregistrer(alleger(partie, champions, "ladder"))
            gardees += 1
        if numero % 25 == 0 or numero == len(nouvelles):
            print(f"   {numero}/{len(nouvelles)} téléchargées, {gardees} gardées")

    classement.vider_cache()   # les statistiques en cache sont périmées
    print(f"Terminé : {parties.compter()} parties en base, {classement.nombre()} joueurs classés, "
          f"{riot.appels} appels à l'API Riot.")


if __name__ == "__main__":
    options = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    options.add_argument("--plateforme", default="euw1", choices=sorted(REGIONS))
    options.add_argument("--ligue", default="challenger", choices=["challenger", "grandmaster", "master"])
    options.add_argument("--joueurs", type=int, default=30)
    options.add_argument("--par-joueur", type=int, default=20)
    options.add_argument("--parties", type=int, default=600)
    try:
        collecter(options.parse_args())
    except RiotErreur as erreur:
        sys.exit(str(erreur))

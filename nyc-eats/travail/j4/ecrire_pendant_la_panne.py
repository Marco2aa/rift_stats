"""J4 matin, exercice 7 : écrire dans MongoDB toutes les secondes pendant la panne du primaire.

Lancer depuis un terminal (profils mongo et python démarrés) :
    docker exec python python /travail/j4/ecrire_pendant_la_panne.py
Le script écrit 40 documents dans la collection journal_panne (un par seconde) et affiche, pour
chaque écriture, le serveur primaire qui l'a reçue et le temps qu'elle a pris.
"""
import datetime
import os
import time

from pymongo import MongoClient

# L'adresse du replica set entier (les trois nœuds) : le pilote trouve seul le primaire.
client = MongoClient(os.environ["MONGO_URI"], serverSelectionTimeoutMS=30000)
journal = client["nyceats"]["journal_panne"]
journal.drop()

debut = time.time()
for numero in range(1, 41):
    depart = time.time()
    try:
        journal.insert_one({"numero": numero, "ecrit_le": datetime.datetime.now()})
        etat = "ok, primaire : %s" % client.primary[0]
    except Exception as erreur:
        etat = "échec : %s" % type(erreur).__name__
    duree = time.time() - depart
    print("%5.1f s  écriture %2d  %-24s (%.1f s)" % (depart - debut, numero, etat, duree), flush=True)
    time.sleep(1)

print("Documents dans journal_panne :", journal.count_documents({}))

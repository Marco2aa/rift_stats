# Worker de NYC Eats : attend les réservations déposées dans la file Redis et les traite une par une.
# Livret de TP J2 après-midi, exercice 8.
#
# Lancement, depuis un terminal (Ctrl+C pour l'arrêter) :
#   docker exec -it python python /travail/j2/worker_reservations.py
import json
import os
import time

import redis

FILE = "file:reservations"

r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
nom_worker = f"worker-{os.getpid()}"
print(f"{nom_worker} : en attente de réservations dans {FILE} (Ctrl+C pour arrêter)", flush=True)

try:
    while True:
        # BRPOP bloque jusqu'à ce qu'une réservation arrive (timeout=0 : attendre sans limite)
        _, texte = r.brpop(FILE, timeout=0)
        reservation = json.loads(texte)
        nom = r.hget(f"resto:{reservation['restaurant']}", "nom") or reservation["restaurant"]
        time.sleep(0.5)   # simule la vérification des tables libres
        r.rpush("reservations:confirmees", texte)
        print(f"{time.strftime('%H:%M:%S')} {nom_worker} : {reservation['pseudo']}, "
              f"{reservation['couverts']} couverts chez {nom} à {reservation['heure']}", flush=True)
except KeyboardInterrupt:
    print(f"{nom_worker} : arrêté.", flush=True)

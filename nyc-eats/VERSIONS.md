# Versions du kit NYC Eats

Figées le 20/10/2026 et validées en réel sur Docker 29.1.3 (Windows 11, WSL2).

| Composant | Image / version | Mémoire max |
|---|---|---|
| MongoDB (3 nœuds, replica set `rs0`) | `mongo:8.0.34` (mongosh inclus) | 600 Mo par nœud |
| Redis | `redis:8.8.3` (AOF activé, `maxmemory 200mb` : Redis refuse les écritures plutôt que d'être tué) | 256 Mo |
| Redis Insight | `redis/redisinsight:3.8.0` | 256 Mo |
| PostgreSQL + pgvector | `pgvector/pgvector:0.8.7-pg18-trixie` (PostgreSQL 18.6, vector 0.8.7) | 384 Mo |
| Python | image construite `nyc-eats-python:2026.11` sur `python:3.13.16-slim` (1,1 Go) | 768 Mo |

Bibliothèques Python : voir `python/requirements.txt` (pymongo 4.19.0, redis 8.1.0, psycopg 3.3.6,
pgvector 0.5.1, numpy 2.5.4, pandas 3.0.6, fastapi 0.150.0, uvicorn 0.54.0, streamlit 1.66.0,
jupyterlab 4.6.4).

## Vérifié le 20/10/2026

- `docker compose --profile tous up -d` : les 7 services démarrent, `mongo-init` crée le replica set
  puis s'arrête (`Exited (0)`) ; aux démarrages suivants il affiche « Replica set déjà créé ».
- `mongoimport` des 25 359 restaurants depuis `/donnees/mongo/restaurants.json` : 2 secondes.
- Depuis le conteneur `python` : PyMongo voit le primaire, Redis répond, `CREATE EXTENSION vector`
  fonctionne dans PostgreSQL.
- Jupyter (8888) et Redis Insight (5540) répondent.
- Panne : `docker stop mongo1` → `mongo2` élu primaire en moins de 15 s, les écritures passent ;
  `docker start mongo1` → `mongo1` redevient primaire (priorité 2).
- `docker compose --profile tous down` puis `up` : données et replica set conservés (volumes nommés).
- Mémoire réelle, tout démarré, bases chargées : environ 0,7 Go.

## À savoir

- Redis Insight affiche d'abord sa licence, à accepter ; ensuite la connexion « NYC Eats » est déjà
  configurée.
- Mac à puce Apple : toutes les images existent en version arm64 native, et les 119 bibliothèques
  Python de l'image ont une version arm64 (vérifié le 20/10/2026). Pas de Rosetta nécessaire.

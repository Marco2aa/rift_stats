# Rift Stats

Tableau de bord League of Legends construit sur le kit NYC Eats : MongoDB (replica set de 3 nœuds), Redis et PostgreSQL avec pgvector, plus une API FastAPI et une interface Streamlit.

## Contenu

| Chemin | Rôle |
|---|---|
| `Rift_Stats_presentation.pdf` | Support de l'oral (13 diapositives) |
| `Rift_Stats_discours.txt` | Texte à lire pendant l'oral, avec les questions probables à la fin |
| `TP_J3_matin_reponses.md` | Journal : réponses du TP et étapes du projet |
| `nyc-eats/projet/rift_stats/` | DAO (Mongo, Redis, PostgreSQL), client Riot, routes `/lol` |
| `nyc-eats/projet/lol_tableau_de_bord.py` | Interface Streamlit |
| `nyc-eats/travail/lol/` | Scripts de chargement (Data Dragon) et de collecte (API Riot) |

## Lancer le projet

Toutes les commandes se tapent dans le dossier `nyc-eats`.

1. **Clé Riot.** Copier `riot.env.example` en `riot.env` et y mettre votre propre clé, à générer sur https://developer.riotgames.com. Une clé de développement expire au bout de 24 h. Le fichier `riot.env` est ignoré par git : ne le committez jamais.

2. **Démarrer les conteneurs.**
   ```
   docker compose --profile tous up -d
   ```

3. **Charger les champions et les objets** dans PostgreSQL (Data Dragon, sans clé) :
   ```
   docker exec -w /travail/lol python python charger_champions.py
   ```

4. **Collecter les parties** du ladder dans MongoDB et Redis. Cela fait environ 570 appels et prend environ 12 minutes à cause du quota de la clé :
   ```
   docker exec --env-file riot.env -w /travail/lol python python collecte_riot.py
   ```

5. **Lancer l'API**, dans un premier terminal :
   ```
   docker exec -it --env-file riot.env python uvicorn api:app --app-dir /projet --host 0.0.0.0 --port 8000 --reload --reload-dir /projet
   ```

6. **Lancer l'interface**, dans un second terminal :
   ```
   docker exec -it python streamlit run /projet/lol_tableau_de_bord.py --server.address 0.0.0.0 --server.port 8501
   ```

Ensuite, ouvrir http://localhost:8501 pour l'interface et http://localhost:8000/docs pour la documentation de l'API.

Rift Stats n'est pas approuvé par Riot Games et ne reflète pas les opinions de Riot Games.

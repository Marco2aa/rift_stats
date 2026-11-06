# Squelette du projet NYC Eats

Une application complète et qui fonctionne dès le départ : trois bases, une API, un tableau de
bord. Pour le projet du vendredi, vous l'adaptez à votre sujet au lieu de partir de zéro.

```
navigateur ──> tableau de bord (Streamlit, port 8501)
                   │  appels HTTP
                   v
               API (FastAPI, port 8000)
                   │  méthodes des classes DAO (nyc_eats/dao.py)
        ┌──────────┼──────────────┐
        v          v              v
     MongoDB     Redis        PostgreSQL
     fiches      cache,       avis (JSONB),
                 compteurs    vecteurs (pgvector)
```

## Les fichiers

| Fichier | Rôle |
|---|---|
| `nyc_eats/connexions.py` | Les connexions aux trois bases (adresses lues dans les variables du conteneur). |
| `nyc_eats/dao.py` | Toutes les requêtes, une classe par base : `RestaurantDAO` (MongoDB), `CacheRedis` (Redis), `AvisDAO` (PostgreSQL). |
| `api.py` | Les routes de l'API. Elles n'appellent que les classes DAO. |
| `tableau_de_bord.py` | Le tableau de bord. Il n'appelle que l'API. |

## Lancer l'application

Dans le dossier `nyc-eats`, depuis un terminal :

1. Démarrer tout le kit : `docker compose --profile tous up -d`
2. Si ce n'est pas déjà fait, charger les données :
   - `docker exec mongo1 mongoimport --db nyceats --collection restaurants --drop --file /donnees/mongo/restaurants.json`
   - `docker exec postgres psql -U nyc -d nyceats -f /donnees/postgres/charger_nyceats.sql`
3. Lancer l'API, dans un **deuxième terminal** (il reste occupé tant que l'API tourne) :
   `docker exec -it python uvicorn api:app --app-dir /projet --host 0.0.0.0 --port 8000 --reload --reload-dir /projet`
4. Vérifier : http://localhost:8000/sante doit afficher le nombre de restaurants, `true` pour
   Redis et le nombre d'avis. La documentation de l'API est sur http://localhost:8000/docs
   (elle a besoin d'internet pour s'afficher).
5. Lancer le tableau de bord, dans un **troisième terminal** :
   `docker exec -it python streamlit run /projet/tableau_de_bord.py --server.address 0.0.0.0 --server.port 8501`
6. Ouvrir http://localhost:8501

Les erreurs de l'API et du tableau de bord s'affichent dans leur terminal. Pour les arrêter :
Ctrl+C dans ce terminal (Ctrl aussi sur Mac). `--reload --reload-dir /projet` relance l'API à
chaque modification d'un fichier du projet ; le tableau de bord se recharge avec le bouton
« Rerun » en haut à droite.

Si vous les avez lancés en arrière-plan (avec `-d` au lieu de `-it`), leurs erreurs ne
s'affichent nulle part : pour les arrêter, `docker restart python` (Jupyter redémarre aussi, vos
notebooks enregistrés ne sont pas perdus).

## Adapter à votre sujet

1. Chargez vos données dans vos bases (au moins deux, dont MongoDB).
2. Écrivez vos requêtes dans `nyc_eats/dao.py` : une méthode par question métier.
3. Exposez-les dans `api.py` : une route par méthode utile.
4. Affichez au moins une métrique calculée dans `tableau_de_bord.py`.

En cas de problème : relancez l'API ou le tableau de bord avec `-it` pour voir l'erreur.

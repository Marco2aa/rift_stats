# TP J3 matin · MongoDB : documents et requêtes

Réponses aux exercices et journal des commandes lancées.

---

## Préparation : import des restaurants

Au départ, la base `nyceats` était vide (`show dbs` n'affichait que `admin`, `config` et `local`). Les conteneurs `mongo1`, `mongo2` et `mongo3` tournaient déjà.

Commande lancée :
```
docker exec mongo1 mongoimport --db nyceats --collection restaurants --drop --file /donnees/mongo/restaurants.json
```
Résultat :
```
dropping: `nyceats.restaurants`
25359 document(s) imported successfully. 0 document(s) failed to import.
```

---

## Partie 1 · Le modèle document

### Exercice 1 : Lire un document

1. Le document a **7 champs** au premier niveau : `_id`, `address`, `borough`, `cuisine`, `grades`, `name`, `restaurant_id`.
2. **Document imbriqué** : `address`, qui contient `building`, `coord`, `street` et `zipcode`. **Tableaux** : `grades`, un tableau de 5 documents, et `address.coord`, un tableau de 2 nombres.
3. Les types des valeurs :

   | Valeur | Type |
   |---|---|
   | `'1007'` | chaîne de caractères (String) |
   | `[ -73.856077, 40.848447 ]` | tableau de nombres décimaux (Array de Double) |
   | `ISODate('2014-03-03T00:00:00.000Z')` | date (Date) |
   | `2` | nombre entier (Int32) |

   `coord` contient la **longitude** puis la **latitude**. C'est l'ordre GeoJSON utilisé par MongoDB.
4. Le restaurant a eu **5 inspections**. La plus récente date du **3 mars 2014** (grade A, score 2).
5. La meilleure inspection est celle du **3 mars 2014**, avec le score le plus bas : **2** (grade A).

Vérification : 7 champs, 5 inspections.

### Exercice 2 : Du tableau au document

1. Le document :
```js
{
  address: {
    building: '3',
    street: 'East 52 Street',
    zipcode: '10022'
  },
  borough: 'Manhattan',
  cuisine: 'French',
  grades: [
    { date: ISODate('2014-04-09T00:00:00.000Z'), grade: 'A', score: 10 },
    { date: ISODate('2013-03-05T00:00:00.000Z'), grade: 'A', score: 9 },
    { date: ISODate('2012-02-02T00:00:00.000Z'), grade: 'A', score: 13 }
  ],
  name: 'La Grenouille',
  restaurant_id: '40365264'
}
```
2. Dans la seconde table, `restaurant_id` était une **clé étrangère** qui reliait chaque inspection à son restaurant. Dans le document, elle **disparaît** : les inspections sont rangées dans le restaurant lui-même. On n'a plus besoin de **jointure** (`JOIN`) pour afficher la fiche.
3. Un code postal est un **identifiant**, pas une quantité : on ne fait pas de calcul dessus, et un nombre perdrait les zéros en tête (`'02134'` deviendrait `2134`). `score` est une **mesure** : on veut le comparer, le trier et en faire une moyenne, donc c'est un nombre.
4. Le champ `_id` est **ajouté automatiquement à l'insertion**. Tout document MongoDB doit avoir un `_id`, et si on n'en fournit pas, `mongoimport` (ou le driver) génère un `ObjectId`. Ce sont 12 octets : un horodatage, une valeur aléatoire et un compteur.

   | `_id` | `restaurant_id` |
   |---|---|
   | clé technique créée par MongoDB | identifiant métier, fourni par la ville de New York |
   | unicité garantie, avec un index créé automatiquement | simple champ : MongoDB ne garantit pas son unicité sans index unique |
   | de type `ObjectId` | de type String |
   | change à chaque import | stable d'un import à l'autre |

5. Le vocabulaire :

   | En SQL | Dans MongoDB |
   |---|---|
   | base de données | base de données |
   | table | collection |
   | ligne | document |
   | colonne | champ |
   | clé primaire | `_id` |
   | jointure | document imbriqué ou tableau (ou `$lookup` dans un pipeline d'agrégation) |

Vérification : 6 champs au premier niveau et 3 éléments dans `grades`.

---

## Partie 2 · Entrer dans MongoDB

### Exercice 3 : Premiers pas dans mongosh

**1.** Commande : `docker exec -it mongo1 mongosh nyceats`

L'invite affichée est :
```
rs0 [direct: primary] nyceats>
```
- `rs0` : le nom du *replica set*, le groupe des trois serveurs `mongo1`, `mongo2` et `mongo3`.
- `[direct: primary]` : on est connecté directement à `mongo1`, qui est le **primaire**, le seul serveur qui accepte les écritures.
- `nyceats` : la base courante, celle sur laquelle porte `db`.

**2.** `show dbs` affiche :
```
admin, config, local, nyceats
```
Les trois premières sont les bases internes de MongoDB. `nyceats` vient de l'import : MongoDB crée une base dès qu'on y écrit un premier document.

**3.** `show collections` et `db.restaurants.countDocuments()` donnent :
```
restaurants
25359
```

**4.** `db.restaurants.findOne({ restaurant_id: "30075445" })`

On retrouve le **même document** : mêmes champs, mêmes valeurs, mêmes 5 inspections. Seul le **`_id` change** :
- sur ce poste : `ObjectId('6aeaf62029f1e35718ad5a81')`
- dans le livret : `ObjectId('6ad71b7d115d0170dcb36491')`

L'`ObjectId` est généré au moment de l'import : il contient l'horodatage de l'insertion et une partie aléatoire. Il diffère donc d'un poste à l'autre, et d'un import à l'autre.

**5.** `db.restaurants.findOne({ restaurant_id: "40365264" }, { _id: 0 })`

Résultat :
```js
{
  address: {
    building: '3',
    coord: [ -73.97557069999999, 40.7596796 ],
    street: 'East   52 Street',
    zipcode: '10022'
  },
  borough: 'Manhattan',
  cuisine: 'French',
  grades: [
    { date: ISODate('2014-04-09T00:00:00.000Z'), grade: 'A', score: 10 },
    { date: ISODate('2013-03-05T00:00:00.000Z'), grade: 'A', score: 9 },
    { date: ISODate('2012-02-02T00:00:00.000Z'), grade: 'A', score: 13 }
  ],
  name: 'La Grenouille',
  restaurant_id: '40365264'
}
```
Ce document correspond à celui de l'exercice 2, à deux différences près :
- un champ en plus, `address.coord`, qu'on avait laissé de côté ;
- la rue est écrite `'East   52 Street'`, avec plusieurs espaces : ce sont les données brutes de la ville.

**6.** Commandes lancées dans un second terminal, deux fois de suite :
```
docker exec mongo1 mongoimport --db nyceats --collection essai_import --file /donnees/mongo/restaurants.json
```
Chaque import affiche : `25359 document(s) imported successfully. 0 document(s) failed to import.`

Ensuite, `db.essai_import.countDocuments()` affiche **50718**, soit 2 × 25359.

MongoDB n'a signalé aucun doublon parce que, pour lui, il n'y en a pas. Le fichier ne contient pas de `_id`, donc chaque import génère un nouvel `ObjectId` pour chaque document. La seule contrainte d'unicité porte sur `_id`, et aucun index unique n'existe sur `restaurant_id`.

`--drop` supprime la collection avant l'import. On repart ainsi d'une collection vide et on peut relancer l'import sans dupliquer les données.

**7.** `db.essai_import.drop()` renvoie `true` : la collection est supprimée.

Vérification : `restaurants` compte 25359 documents et `essai_import` en comptait 50718, le double.

---

## Projet du vendredi (06/11) · Rift Stats, League of Legends

Sujet choisi : les statistiques des champions (taux de victoire par champion et par rôle) et le classement des joueurs. Données : API Riot (Match-V5, League-V4) et Data Dragon.

### Étape 1 : l'interface

Fichiers créés (le tableau de bord NYC Eats n'a pas été modifié) :
- `nyc-eats/projet/lol_tableau_de_bord.py` : le tableau de bord Streamlit.
- `nyc-eats/projet/.streamlit/config.toml` : le thème sombre et doré.

Lancement :
```
docker exec -it -w /projet python streamlit run lol_tableau_de_bord.py --server.address 0.0.0.0 --server.port 8501
```
puis ouvrir http://localhost:8501.

Contenu :
- en haut, 4 chiffres clés (parties, champions, joueurs, meilleur taux de victoire) ;
- l'onglet Champions : le top 10 des champions par taux de victoire et la liste complète, avec les icônes ;
- l'onglet Classement : le podium et le top 10 des joueurs par LP ;
- l'onglet Fiche champion : les statistiques d'un champion et les champions qui lui ressemblent.

Tant que les routes `/lol/...` de l'API n'existent pas, la page affiche des **données de démonstration inventées**, avec un badge rouge. Les routes attendues sont listées en tête du fichier.

Vérification : le script a été exécuté avec `streamlit.testing` (AppTest), avec plusieurs filtres, sans aucune exception.

### Étape 2 : branchement sur les vraies données, et animations

**L'API Riot.** Sans clé, elle répond `HTTP 401` : il faut une clé de développement (developer.riotgames.com, valable 24 h). Data Dragon, lui, est accessible sans clé (version 16.22.1).

**Fichiers ajoutés :**

| Fichier | Rôle |
|---|---|
| `projet/rift_stats/dao.py` | Une classe par base : `PartieDAO` (MongoDB, base `riftstats`, collection `parties`), `ClassementRedis` (ensemble trié `lol:classement`, hash `lol:joueur:<puuid>`, cache `lol:cache:*`), `ChampionDAO` (PostgreSQL, table `lol_champions` avec un vecteur pgvector). |
| `projet/rift_stats/routes.py` | Les routes `/lol/sante`, `/lol/champions`, `/lol/champions/stats`, `/lol/classement`, `/lol/champions/{id}/similaires`. |
| `projet/api.py` | Une ligne ajoutée : `app.include_router(routes_lol)`. |
| `travail/lol/charger_champions.py` | Data Dragon → PostgreSQL, sans clé. |
| `travail/lol/collecte_riot.py` | API Riot → Redis (classement) et MongoDB (parties allégées). |

**Choix de modélisation :**
- **Le document** : une partie par document, avec `_id` = l'identifiant Riot de la partie (`matchId`). Le document contient les 10 joueurs imbriqués et n'en garde que 13 champs (une partie Riot en fait plus de 1 000).
- **Pas de doublon** : la collecte enregistre avec `replace_one(..., upsert=True)`. On peut donc la relancer sans doublon, ce qui répond au problème vu à l'exercice 3.6.
- **Les parties annulées** : les « remakes » (moins de 5 minutes) sont ignorés, pour ne pas fausser les taux de victoire.
- **Le taux de victoire** : agrégation MongoDB avec `$unwind` sur `participants`, puis deux `$group` (par champion et par rôle, puis par champion en gardant le rôle le plus joué). Le résultat est mis en cache 60 s dans Redis.
- **La similarité** : le vecteur d'un champion contient ses 6 classes (0 ou 1) et ses 4 notes Data Dragon divisées par 10. pgvector compare ces vecteurs avec la distance `<->`.

**Commandes lancées :**
```
docker exec python python /travail/lol/charger_champions.py
→ Data Dragon 16.22.1 : 173 champions chargés dans PostgreSQL (table lol_champions).
```

**Tests effectués :**
- **Les routes** : toutes répondent. `/lol/champions/Ahri/similaires` donne Aurora, Sylas, Kassadin, Katarina…, et un champion inconnu renvoie 404.
- **L'agrégation** : je l'ai testée sur une base séparée (`riftstats_test`, supprimée ensuite). Avec 3 parties, dont une enregistrée deux fois, la base compte bien 3 parties, et les chiffres sont justes (2 victoires sur 3 = 66,7 %, KDA 7,5).
- **L'interface** : testée dans l'état « démonstration » (sans API) et dans l'état « API connectée » (avec API), sans aucune exception.

**Les animations, toutes en CSS :**
- un titre au reflet doré et un balayage lumineux sur le bandeau ;
- un badge d'état dont le point pulse ;
- des compteurs qui défilent de 0 jusqu'à leur valeur ;
- des tuiles qui apparaissent l'une après l'autre ;
- des barres du top 10 qui se remplissent ;
- un podium dont le n°1 brille ;
- un anneau doré qui tourne autour de l'icône du champion ;
- des effets au survol.

Les animations sont coupées si le système demande de réduire les animations.

**Pour avoir les vraies statistiques :**
```
docker exec -it -e RIOT_API_KEY=RGAPI-... python python /travail/lol/collecte_riot.py
```

### Étape 3 : la collecte réelle

- **La clé** est rangée dans `nyc-eats/riot.env`, hors de `projet/` et `travail/`. Ce fichier ne doit pas être rendu.
- **La première clé** a été refusée (`401 Unknown apikey`). **La seconde** a été acceptée une minute après sa création.
- **La commande** : `docker exec --env-file riot.env python python -u /travail/lol/collecte_riot.py`
- **Le résultat** : 300 joueurs Challenger EUW dans Redis, et les parties de 30 joueurs (environ 513) dans MongoDB.

### Étape 4 : nouvelles fonctionnalités

| Fonctionnalité | Base utilisée | Technique |
|---|---|---|
| **Profil joueur** (recherche par Riot ID, rang, champions favoris, 20 dernières parties) | Redis + MongoDB | `ZREVRANK` pour le rang ; `$regex` sur `participants.pseudo` ; `$filter` pour extraire la ligne du joueur ; index multiclé sur `participants.puuid` |
| **Objets clés** d'un champion | MongoDB + PostgreSQL | double `$unwind` (participants puis objets) ; noms et prix des objets dans la table `lol_objets` (Data Dragon) |
| **Victoire selon la durée** | MongoDB | `$bucket` par tranche de 5 minutes |
| **Matchups** (adversaire direct, même rôle) | MongoDB | `$expr` qui compare deux champs du même document (rôle égal, équipe différente) |
| **Onglet Infra** | les 3 | `replSetGetStatus` (primaire et secondaires), `$collStats`, `INFO memory`, `pg_total_relation_size` |

Toutes les réponses (sauf l'infra) sont mises en cache 60 s dans Redis.

Exemples obtenus sur les vraies données :
- Ahri gagne 25 % de ses parties de moins de 20 minutes, mais 71 % de celles de 30 à 35 minutes : c'est un champion de fin de partie.
- Kaori#EUW33 (n°1, 4336 LP) : 20 parties collectées, 45 % de victoires, KDA 2,34, joue surtout tireur (Tristana, Yunara, Kalista…).

Index MongoDB créés : `participants.puuid`, `participants.champion_id`, `date`.

### Étape 5 : barre de recherche (champions et joueurs, y compris soi-même)

Elle est placée en haut de la page et cherche dans trois sources à la fois :
- **les champions** : le nom est comparé sans accents ni majuscules (« zoe » trouve Zoé) ;
- **les joueurs déjà en base** : `$regex` sur `participants.pseudo` dans MongoDB ;
- **n'importe quel Riot ID** `Pseudo#TAG`, sur les serveurs Riot : il suffit de choisir le serveur (EUW par défaut) puis de cliquer sur « Charger ».

Le chargement d'un Riot ID passe par la nouvelle route `POST /lol/riot/joueur`. Elle fait 4 choses :
1. récupère le compte (Account-V1) ;
2. récupère le rang officiel (League-V4), gardé 10 min dans Redis (`lol:rang:<puuid>`) ;
3. récupère les 15 dernières parties classées, ou tous modes si le joueur n'a joué aucune classée ;
4. range ces parties dans MongoDB avec `origine: "recherche"`.

Pourquoi `origine: "recherche"` ? Les statistiques des champions filtrent `origine != "recherche"`. Un joueur cherché ne fausse donc pas les statistiques des Challenger. Les 510 parties de la collecte ont été marquées `origine: "ladder"`.

Pourquoi `POST` et pas `GET` ? La route écrit en base et consomme le quota de la clé Riot.

Le client Riot est désormais dans `projet/rift_stats/riot.py`, partagé par l'API et le script de collecte.

**L'API doit être lancée avec la clé** (depuis le dossier `nyc-eats`) :
```
docker exec -it --env-file riot.env python uvicorn api:app --app-dir /projet --host 0.0.0.0 --port 8000 --reload --reload-dir /projet
```

**Tests effectués :**
- recherche « zoe » → Zoé ;
- recherche « kaori » → Kaori#EUW33 ;
- Riot ID inconnu → message « Riot ID introuvable sur ce serveur » ;
- SUPKING#ggez → Gold III, 97 LP, 15 parties.

**Démonstration CAP pour la soutenance :** lancer `docker stop mongo1`, puis cliquer sur « Rafraîchir » dans l'onglet Infra. On y voit mongo1 hors ligne et un secondaire élu primaire. Relancer ensuite avec `docker start mongo1`.

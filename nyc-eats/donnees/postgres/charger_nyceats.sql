-- Charge les tables PostgreSQL de NYC Eats (J4 après-midi et projet).
-- Relançable : repart de zéro à chaque fois.
--
--   docker exec postgres psql -U nyc -d nyceats -f /donnees/postgres/charger_nyceats.sql
--
-- restaurants  : 2 000 restaurants de Manhattan et Brooklyn (extrait de MongoDB), avec un « profil »
--                vectoriel (moyenne des vecteurs de leurs avis)
-- avis         : 6 001 avis clients ; le détail est en JSON (JSONB), le texte a son vecteur
-- reservations : 3 000 réservations de novembre 2026
-- requetes     : 10 recherches types, avec leur vecteur (calculé à l'avance)
-- Les vecteurs ont 384 dimensions (modèle paraphrase-multilingual-MiniLM-L12-v2).

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS reservations, avis, requetes, restaurants CASCADE;

CREATE TABLE restaurants (
    restaurant_id text PRIMARY KEY,
    nom           text NOT NULL,
    cuisine       text NOT NULL,
    quartier      text NOT NULL,
    code_postal   text,
    profil        vector(384)
);

CREATE TABLE avis (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id text NOT NULL REFERENCES restaurants,
    note          smallint NOT NULL CHECK (note BETWEEN 1 AND 5),
    publie_le     date NOT NULL,
    contenu       jsonb NOT NULL,
    embedding     vector(384)
);

CREATE TABLE reservations (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    restaurant_id text NOT NULL REFERENCES restaurants,
    client        text NOT NULL,
    jour          date NOT NULL,
    heure         time NOT NULL,
    couverts      smallint NOT NULL CHECK (couverts > 0),
    statut        text NOT NULL
);

CREATE TABLE requetes (
    id        integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    texte     text NOT NULL,
    embedding vector(384) NOT NULL
);

COPY restaurants (restaurant_id, nom, cuisine, quartier, code_postal, profil)
    FROM '/donnees/postgres/restaurants.csv' WITH (FORMAT csv, HEADER true);
COPY avis (restaurant_id, note, publie_le, contenu, embedding)
    FROM '/donnees/postgres/avis.csv' WITH (FORMAT csv, HEADER true);
COPY reservations (restaurant_id, client, jour, heure, couverts, statut)
    FROM '/donnees/postgres/reservations.csv' WITH (FORMAT csv, HEADER true);
COPY requetes (texte, embedding)
    FROM '/donnees/postgres/requetes.csv' WITH (FORMAT csv, HEADER true);

SELECT 'restaurants' AS "table", count(*) AS lignes FROM restaurants
UNION ALL SELECT 'avis', count(*) FROM avis
UNION ALL SELECT 'reservations', count(*) FROM reservations
UNION ALL SELECT 'requetes', count(*) FROM requetes;

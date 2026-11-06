// Crée le replica set rs0 (mongo1, mongo2, mongo3) s'il n'existe pas encore.
// Lancé une fois par le service mongo-init ; sans effet aux démarrages suivants.
try {
  const etat = rs.status();
  print("Replica set déjà créé : " + etat.set);
} catch (e) {
  rs.initiate({
    _id: "rs0",
    members: [
      { _id: 0, host: "mongo1:27017", priority: 2 },
      { _id: 1, host: "mongo2:27017", priority: 1 },
      { _id: 2, host: "mongo3:27017", priority: 1 }
    ]
  });
  let essais = 0;
  while (!db.hello().isWritablePrimary && essais < 60) {
    sleep(1000);
    essais++;
  }
  print("Replica set rs0 créé, primaire : " + db.hello().primary);
}

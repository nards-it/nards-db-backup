db = db.getSiblingDB('admin'); // Seleziona il database 'admin'

const username = process.env.MONGO_INITDB_ROOT_USERNAME;
const password = process.env.MONGO_INITDB_ROOT_PASSWORD;

let userExists = db.system.users.findOne({ user: username, db: "admin" });

if (!userExists) {
  print(`User ${username} does not exist. Creating user...`);
  db.createUser({
    user: username,
    pwd: password,
    roles: [
      { role: 'readWriteAnyDatabase', db: 'admin' },
      { role: 'dbAdminAnyDatabase', db: 'admin' },
      { role: 'userAdminAnyDatabase', db: 'admin' }
    ],
  });
  print(`User ${username} created successfully.`);
} else {
  print(`User ${username} already exists.`);
}

// Creare un database e una collezione di esempio per il test end-to-end
db = db.getSiblingDB('e2e_test_db');
print(`Switched to db 'e2e_test_db'. Creating collection 'sample_items'.`);
db.createCollection('sample_items');
db.sample_items.insertOne({ name: "Test Item 1", value: 123 });
db.sample_items.insertOne({ name: "Test Item 2", value: 456 });
print("Collection 'sample_items' created and documents inserted into 'e2e_test_db'.");

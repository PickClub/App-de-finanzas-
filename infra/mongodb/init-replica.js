// Only administrative commands against the newly created development instance.
const admin = db.getSiblingDB('admin');
const expectedSet = 'app_finanzas_dev_rs';
const expectedHost = 'mongodb-dev:27017';
let status;
try {
  status = admin.runCommand({ replSetGetStatus: 1 });
} catch (error) {
  if (error.code !== 94) throw error;
  status = { ok: 0, code: 94 };
}
if (status.ok !== 1) {
  if (status.code !== 94) throw new Error('Unexpected replica set status; refusing initialization.');
  const result = admin.runCommand({
    replSetInitiate: { _id: expectedSet, members: [{ _id: 0, host: expectedHost }] },
  });
  if (result.ok !== 1) throw new Error('Replica set initialization failed.');
}
for (let attempt = 0; attempt < 60; attempt++) {
  const hello = admin.runCommand({ hello: 1 });
  if (hello.setName && hello.setName !== expectedSet) throw new Error('Wrong replica set; refusing to continue.');
  if (hello.isWritablePrimary && hello.setName === expectedSet) {
    status = admin.runCommand({ replSetGetStatus: 1 });
    const config = admin.runCommand({ replSetGetConfig: 1 });
    if (status.ok !== 1 || config.ok !== 1 || config.config.members.length !== 1 ||
        config.config.members[0].host !== expectedHost) throw new Error('Unexpected replica configuration.');
    print('Development replica set ready: ' + expectedSet + ', PRIMARY, one member.');
    quit(0);
  }
  sleep(1000);
}
throw new Error('Timed out waiting for development PRIMARY.');

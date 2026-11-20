// Execute the real Notes handlers with synthetic storage, including delayed/failing writes.
const assert = require('node:assert/strict');
const { fixture, note } = require('./test-note-persistence.cjs');
const copy = value => JSON.parse(JSON.stringify(value));
(async () => {
  const selected = note('selected');
  const neighbor = { ...note('neighbor'), content: 'Neighbor unchanged' };
  let f = fixture([selected, neighbor], copy(selected));
  for (const expected of [true, false]) {
    await f.run.togglePin(selected.id);
    assert.equal(f.ctx.previewNote.pinned, expected, 'Open preview must reflect the confirmed pin state');
    assert.equal(f.snapshot()[0].pinned, expected);
    assert.deepEqual(f.snapshot()[1], neighbor);
    assert.equal(f.ctx.previewNote.content, selected.content);
  }
  for (const failure of [async () => false, async () => { throw Error('Synthetic storage failure'); }]) {
    f = fixture([selected, neighbor], copy(selected));
    f.ctx.storage.setItem = failure;
    await f.run.togglePin(selected.id);
    assert.equal(f.ctx.previewNote.pinned, false);
    assert.deepEqual(f.snapshot(), [selected, neighbor]);
    assert.deepEqual(copy(f.ctx.notes), [selected, neighbor]);
    assert.equal(f.alerts.length, 1);
  }
  f = fixture([selected, neighbor], copy(selected));
  let finish;
  const store = f.ctx.storage.setItem;
  f.ctx.storage.setItem = async (...args) => { await new Promise(resolve => { finish = resolve; }); return store(...args); };
  const pending = f.run.togglePin(selected.id);
  assert.equal(f.ctx.previewNote.pinned, false, 'Do not update before storage confirms');
  await f.run.togglePin(selected.id);
  f.ctx.previewNote = copy(neighbor);
  finish(); await pending;
  assert.equal(f.writes, 1, 'Rapid taps must not produce extra writes');
  assert.deepEqual(copy(f.ctx.previewNote), neighbor, 'Do not replace a different preview opened during storage');
  f = fixture([selected, neighbor], copy(selected));
  const confirmed = f.ctx.storage.setItem;
  f.ctx.storage.setItem = async (...args) => { await new Promise(resolve => { finish = resolve; }); return confirmed(...args); };
  const closing = f.run.togglePin(selected.id);
  f.ctx.previewNote = null;
  finish(); await closing;
  assert.equal(f.ctx.previewNote, null, 'Do not reopen a closed preview');
  console.log('PASS: preview pin/unpin, confirmed-only state, persistence failures, correct entity, rapid taps and closed preview. Synthetic storage only.');
})().catch(error => { console.error(error); process.exitCode = 1; });

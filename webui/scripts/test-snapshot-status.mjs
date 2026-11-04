import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'
import ts from 'typescript'

const code = ts.transpileModule(readFileSync(new URL('../src/lib/snapshotStatus.ts', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.ES2022 },
}).outputText
const { snapshotStatus } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const base = { dueAt: 1600, now: 1000, loaded: true, loopRunning: true }
for (const [input, key] of [
  [{}, 'snapshotMinutes'], [{ dueAt: 1040 }, 'snapshotSoon'], [{ dueAt: 5000 }, 'snapshotHours'],
  [{ dueAt: 1000 }, 'snapshotDue'], [{ dueAt: 980 }, 'snapshotDue'], [{ dueAt: 900 }, 'snapshotDelayed'],
  [{ paused: true }, 'snapshotPaused'], [{ recovering: true }, 'snapshotRecovering'],
  [{ cooling: true }, 'snapshotCooling'], [{ active: true, paused: true }, 'snapshotRunning'],
  [{ dueAt: null }, 'snapshotNone'], [{ dueAt: NaN }, 'snapshotNone'],
  [{ loaded: false }, 'snapshotLoading'], [{ stale: true }, 'snapshotStale'],
  [{ loopRunning: false }, 'snapshotStopped'],
]) {
  const status = snapshotStatus({ ...base, ...input })
  assert.equal(status.key, `statusbar.${key}`)
  if (['snapshotDue', 'snapshotDelayed'].includes(key)) {
    assert.equal(status.label, 'statusbar.snapshotSchedule')
    assert.equal(status.tone, 'warning')
  }
}
assert.equal(snapshotStatus({ ...base, dueAt: 500 }).count, 8)
assert.equal(snapshotStatus({ ...base, dueAt: 1061 }).count, 2)
console.log('17 snapshot schedule checks passed')

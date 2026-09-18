import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
  applyLinearBlendSkinning,
  computeVisiblePeople,
  createMeshApiClient,
  createMockMeshApiClient,
  jointMatricesForPose,
  loadFixtureResult,
  validateMeshResult,
} from '../lib/render-model.mjs';

test('linear blend skinning transforms vertices by weighted joint matrices', () => {
  const vertex = [1, 0, 0];
  const identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const translateX = [1, 0, 0, 2, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
  const result = applyLinearBlendSkinning([vertex], [{ joints: [0, 1], weights: [0.25, 0.75] }], [identity, translateX]);
  assert.deepEqual(result[0].map((n) => Number(n.toFixed(3))), [2.5, 0, 0]);
});

test('schema validation accepts complete and partial mesh results', () => {
  const multi = loadFixtureResult('multi-person');
  const partial = loadFixtureResult('partial-failure');
  assert.doesNotThrow(() => validateMeshResult(multi));
  assert.doesNotThrow(() => validateMeshResult(partial));
  assert.equal(partial.people.find((person) => person.track_id === 'person-gamma').mesh_asset, null);
});

test('viewer helper treats mesh-bearing people as default visible body surfaces', () => {
  const result = loadFixtureResult('multi-person');
  const visible = computeVisiblePeople(result, 'all');
  assert.equal(visible.length, 2);
  assert.ok(visible.every((person) => person.mesh_asset?.faces?.length > 0));
  assert.equal(computeVisiblePeople(result, 'primary')[0].track_id, 'person-alpha');
});

test('viewer skinning uses animated joint poses and inverse bind matrices to deform limbs', () => {
  const result = loadFixtureResult('multi-person');
  const person = result.people[0];
  const mesh = person.mesh_asset;
  const firstPose = result.frames[0].people.find((entry) => entry.track_id === person.track_id);
  const laterPose = result.frames[4].people.find((entry) => entry.track_id === person.track_id);
  const leftHandIndex = mesh.joint_hierarchy.findIndex((joint) => joint.name === 'left_hand');
  const leftHandVertexIndex = mesh.skin_weights.findIndex((row) => row.joints.includes(leftHandIndex));

  assert.notEqual(leftHandIndex, -1);
  assert.notEqual(leftHandVertexIndex, -1);
  assert.notDeepEqual(
    firstPose.joints_3d.find((joint) => joint.name === 'left_hand').position,
    laterPose.joints_3d.find((joint) => joint.name === 'left_hand').position,
  );

  const firstVertices = applyLinearBlendSkinning(mesh.vertices, mesh.skin_weights, jointMatricesForPose(firstPose, mesh.joint_hierarchy, mesh.inverse_bind_matrices, false));
  const laterVertices = applyLinearBlendSkinning(mesh.vertices, mesh.skin_weights, jointMatricesForPose(laterPose, mesh.joint_hierarchy, mesh.inverse_bind_matrices, false));

  assert.notDeepEqual(firstVertices[leftHandVertexIndex], laterVertices[leftHandVertexIndex]);
});

test('upload flow does not ask users to type duration; metadata comes from API result', () => {
  const result = loadFixtureResult('multi-person');
  assert.equal(result.video.duration_seconds, 2);
  const appSource = readFileSync(new URL('../components/StepwiseMeshApp.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(appSource, /setSeconds|Length <input|type="number" min=\{1\} max=\{130\}/);
  assert.match(appSource, /YouTube, TikTok, Instagram/);
});

test('mock API client creates, polls, and returns validated completed jobs', async () => {
  const client = createMockMeshApiClient(loadFixtureResult('single-person'));
  const job = await client.createJob({ source_url: 'https://example.com/dance.mp4' });
  assert.equal(job.stage, 'queued');
  const stages = [];
  for await (const status of client.pollJob(job.job_id)) stages.push(status.stage);
  assert.deepEqual(stages, ['downloading', 'detecting', 'tracking', 'meshing', 'skinning', 'smoothing', 'analyzing', 'packaging', 'complete']);
  const result = await client.getResult(job.job_id);
  assert.equal(result.people[0].mesh_asset.format, 'inline-rest-mesh-v1');
});

test('real API client uploads videos through presigned object storage before creating a job', async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    if (String(url).endsWith('/v1/uploads/presign')) {
      return new Response(
        JSON.stringify({
          method: 'PUT',
          upload_url: 'https://r2.example/upload',
          upload_ref: 'storage://uploads/job-1/dance.mp4',
          object_key: 'uploads/job-1/dance.mp4',
          headers: { 'Content-Type': 'video/mp4' },
          expires_in_seconds: 900,
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      );
    }
    if (String(url) === 'https://r2.example/upload') return new Response(null, { status: 200 });
    if (String(url).endsWith('/v1/jobs')) {
      return new Response(JSON.stringify({ job_id: 'job-1', stage: 'queued', progress: 0, people_detected: 0 }), { status: 200, headers: { 'content-type': 'application/json' } });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  try {
    const client = createMeshApiClient({ baseUrl: 'https://api.stepwise.test', fallbackResult: loadFixtureResult('single-person') });
    const job = await client.createJob({ video_file: { name: 'dance.mp4', type: 'video/mp4', size: 123 } });

    assert.equal(job.job_id, 'job-1');
    assert.equal(calls[0].url, 'https://api.stepwise.test/v1/uploads/presign');
    assert.equal(JSON.parse(calls[0].init.body).filename, 'dance.mp4');
    assert.equal(calls[1].url, 'https://r2.example/upload');
    assert.equal(calls[1].init.method, 'PUT');
    assert.equal(calls[2].url, 'https://api.stepwise.test/v1/jobs');
    assert.deepEqual(JSON.parse(calls[2].init.body), { upload_ref: 'storage://uploads/job-1/dance.mp4' });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('fixture JSON used by app stays in sync with contracts package', () => {
  const appFixture = JSON.parse(readFileSync(new URL('../public/fixtures/multi-person.json', import.meta.url), 'utf8'));
  assert.equal(appFixture.schema_version, 'mesh-result-v1');
});

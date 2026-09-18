import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

const schema = JSON.parse(readFileSync(new URL('../schema/mesh-result-v1.schema.json', import.meta.url), 'utf8'));
const generatedTypes = readFileSync(new URL('../src/mesh-result-v1.ts', import.meta.url), 'utf8');
const fixtureNames = ['single-person', 'multi-person', 'partial-failure', 'no-person'];

function loadFixture(name) {
  return JSON.parse(readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url), 'utf8'));
}

function assertVec(name, value, length) {
  assert.ok(Array.isArray(value), `${name} must be an array`);
  assert.equal(value.length, length, `${name} must have ${length} entries`);
  for (const entry of value) assert.equal(typeof entry, 'number', `${name} entries must be numeric`);
}

function validateMeshResult(result) {
  for (const field of schema.required) assert.ok(field in result, `missing top-level field ${field}`);
  assert.equal(result.schema_version, 'mesh-result-v1');
  assert.equal(typeof result.video.source_url, 'string');
  assert.equal(typeof result.video.playback_url, 'string');
  assert.ok(result.video.duration_seconds >= 0);
  assert.ok(result.video.fps > 0);
  assert.ok(result.video.dimensions.width > 0);
  assert.ok(result.video.dimensions.height > 0);

  const peopleById = new Map(result.people.map((person) => [person.track_id, person]));
  assert.equal(peopleById.size, result.people.length, 'track_id values must be unique');
  for (const person of result.people) {
    assert.match(person.track_id, /^person-[a-z0-9-]+$/);
    assert.match(person.color, /^#[0-9a-fA-F]{6}$/);
    assert.ok(person.confidence >= 0 && person.confidence <= 1);
    assert.ok(person.primary_dancer_score >= 0 && person.primary_dancer_score <= 1);
    assert.ok(Array.isArray(person.visible_frame_ranges));
    if (person.mesh_asset) {
      assert.ok(person.mesh_asset.vertices.length >= 8, 'mesh must contain a skinned body surface, not a skeleton-only payload');
      assert.ok(person.mesh_asset.faces.length >= 6, 'mesh must have faces');
      assert.ok(person.mesh_asset.skin_weights.length === person.mesh_asset.vertices.length, 'one skin weight row per vertex');
      assert.ok(person.mesh_asset.joint_hierarchy.length >= 5, 'joint hierarchy must support skinning');
      assertVec('mesh vertex', person.mesh_asset.vertices[0], 3);
      assert.equal(person.mesh_asset.faces[0].length, 3);
      assert.ok(person.mesh_asset.shape_parameters.height_m > 0);
    }
  }

  for (const frame of result.frames) {
    assert.equal(typeof frame.timestamp_seconds, 'number');
    for (const pose of frame.people) {
      assert.ok(peopleById.has(pose.track_id), `frame references unknown ${pose.track_id}`);
      assert.equal(pose.bbox.length, 4);
      assert.ok(pose.pose_params.length >= 5, 'pose params must include body articulation');
      assertVec('global translation', pose.global_transform.translation, 3);
      assertVec('global rotation', pose.global_transform.rotation, 4);
      assert.ok(pose.visibility >= 0 && pose.visibility <= 1);
      assert.ok(pose.tracking_confidence >= 0 && pose.tracking_confidence <= 1);
    }
  }

  assert.ok(Array.isArray(result.analysis.beats));
  assert.ok(typeof result.analysis.difficulty.overall_score === 'number');
  assert.ok(Array.isArray(result.assets.mesh_asset_urls));
  assert.ok(result.model_report.license_flags.length >= 1, 'license flags are required for production/commercial readiness');
}

for (const name of fixtureNames) {
  validateMeshResult(loadFixture(name));
}

const partial = loadFixture('partial-failure');
assert.ok(partial.people.some((person) => person.mesh_asset === null && person.error), 'partial fixture must keep failed person without failing the job');
assert.ok(partial.people.some((person) => person.mesh_asset), 'partial fixture must keep successful people');

const noPerson = loadFixture('no-person');
assert.equal(noPerson.people.length, 0);
assert.ok(noPerson.model_report.warnings.some((warning) => warning.includes('No people')));

const multi = loadFixture('multi-person');
assert.notDeepEqual(multi.people[0].mesh_asset.vertices, multi.people[1].mesh_asset.vertices, 'fixtures must prove body surfaces are not one fixed generic avatar');
assert.match(generatedTypes, /export interface MeshResultV1/);
assert.match(generatedTypes, /mesh_asset: MeshAssetV1 \| null/);

const before = generatedTypes;
execFileSync('node', ['scripts/generate-types.mjs'], { cwd: new URL('..', import.meta.url), stdio: 'pipe' });
const after = readFileSync(new URL('../src/mesh-result-v1.ts', import.meta.url), 'utf8');
assert.equal(after, before, 'generated TypeScript types are not up to date');

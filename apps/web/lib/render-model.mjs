import { readFileSync } from 'node:fs';

export const JOB_STAGES = ['downloading', 'detecting', 'tracking', 'meshing', 'skinning', 'smoothing', 'analyzing', 'packaging', 'complete'];

export function transformPoint(matrix, point) {
  const [x, y, z] = point;
  return [
    matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3],
    matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7],
    matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11],
  ];
}

export function applyLinearBlendSkinning(vertices, skinWeights, jointMatrices) {
  return vertices.map((vertex, index) => {
    const row = skinWeights[index] ?? { joints: [0], weights: [1] };
    const out = [0, 0, 0];
    row.joints.forEach((jointIndex, weightIndex) => {
      const weight = row.weights[weightIndex] ?? 0;
      const transformed = transformPoint(jointMatrices[jointIndex], vertex);
      out[0] += transformed[0] * weight;
      out[1] += transformed[1] * weight;
      out[2] += transformed[2] * weight;
    });
    return out;
  });
}

export function validateMeshResult(result) {
  const required = ['schema_version', 'video', 'people', 'frames', 'analysis', 'assets', 'model_report'];
  for (const field of required) {
    if (!(field in result)) throw new Error(`MeshResultV1 missing ${field}`);
  }
  if (result.schema_version !== 'mesh-result-v1') throw new Error('Unsupported mesh result schema');
  if (!Array.isArray(result.people) || !Array.isArray(result.frames)) throw new Error('Invalid people/frames arrays');
  for (const person of result.people) {
    if (!person.track_id || typeof person.track_id !== 'string') throw new Error('Invalid person track_id');
    if (!/^#[0-9a-fA-F]{6}$/.test(person.color)) throw new Error(`Invalid color for ${person.track_id}`);
    if (person.mesh_asset) {
      if (!person.mesh_asset.vertices?.length || !person.mesh_asset.faces?.length) throw new Error(`Mesh asset for ${person.track_id} must contain a body surface`);
      if (person.mesh_asset.skin_weights.length !== person.mesh_asset.vertices.length) throw new Error(`Skin weights mismatch for ${person.track_id}`);
    }
  }
  return result;
}

export function loadFixtureResult(name) {
  const url = new URL(`../public/fixtures/${name}.json`, import.meta.url);
  return validateMeshResult(JSON.parse(readFileSync(url, 'utf8')));
}

export function computeVisiblePeople(result, selectedTrackId) {
  const meshPeople = result.people.filter((person) => person.mesh_asset);
  if (selectedTrackId === 'all') return meshPeople;
  if (selectedTrackId === 'primary') {
    return meshPeople.slice().sort((a, b) => b.primary_dancer_score - a.primary_dancer_score).slice(0, 1);
  }
  return meshPeople.filter((person) => person.track_id === selectedTrackId);
}

export function jointMatricesForPose(personFrame, jointHierarchy, inverseBindMatrices, mirror) {
  const mirrorScale = mirror ? -1 : 1;
  return jointHierarchy.map((joint, index) => {
    const poseJoint = personFrame?.joints_3d.find((entry) => entry.name === joint.name);
    const current = poseJoint?.position ?? joint.rest_position;
    const inverseBind = inverseBindMatrices[index] ?? [1, 0, 0, -joint.rest_position[0], 0, 1, 0, -joint.rest_position[1], 0, 0, 1, -joint.rest_position[2], 0, 0, 0, 1];
    return [
      mirrorScale,
      0,
      0,
      current[0] * mirrorScale + inverseBind[3] * mirrorScale,
      0,
      1,
      0,
      current[1] + inverseBind[7],
      0,
      0,
      1,
      current[2] + inverseBind[11],
      0,
      0,
      0,
      1,
    ];
  });
}


export function createMockMeshApiClient(result) {
  const jobs = new Map();
  return {
    async createJob(input) {
      if (!input?.source_url && !input?.upload_ref && !input?.video_file) throw new Error('Paste a link or upload a video.');
      if (input.source_url && !input.source_url.startsWith('http')) throw new Error('source_url must be an http(s) URL');
      const job = { job_id: `job-${jobs.size + 1}`, stage: 'queued', progress: 0, people_detected: 0 };
      jobs.set(job.job_id, { ...job, result: validateMeshResult(result) });
      return job;
    },
    async *pollJob(jobId) {
      if (!jobs.has(jobId)) throw new Error('job not found');
      for (const [index, stage] of JOB_STAGES.entries()) {
        const status = { job_id: jobId, stage, progress: stage === 'complete' ? 100 : Math.round(((index + 1) / JOB_STAGES.length) * 95), people_detected: stage === 'complete' ? result.people.length : Math.min(result.people.length, Math.max(0, index - 1)) };
        jobs.set(jobId, { ...jobs.get(jobId), ...status });
        yield status;
      }
    },
    async getResult(jobId) {
      const job = jobs.get(jobId);
      if (!job) throw new Error('job not found');
      return validateMeshResult(job.result);
    },
  };
}

async function parseJsonResponse(response, fallbackMessage) {
  if (!response.ok) {
    let detail = fallbackMessage;
    try {
      const payload = await response.json();
      detail = payload.detail ?? payload.message ?? detail;
    } catch {
      // keep fallback
    }
    throw new Error(detail);
  }
  return response.json();
}

function joinUrl(baseUrl, path) {
  return `${baseUrl.replace(/\/$/, '')}${path}`;
}

export function createMeshApiClient({ baseUrl, fallbackResult }) {
  if (!baseUrl) return createMockMeshApiClient(fallbackResult);
  return {
    async createJob(input) {
      if (!input?.source_url && !input?.upload_ref && !input?.video_file) throw new Error('Paste a link or upload a video.');
      if (input.video_file) {
        const file = input.video_file;
        const presign = await parseJsonResponse(
          await fetch(joinUrl(baseUrl, '/v1/uploads/presign'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filename: file.name ?? input.upload_ref ?? 'uploaded-video.mp4',
              content_type: file.type || 'application/octet-stream',
              content_length: file.size ?? 0,
            }),
          }),
          'Unable to prepare upload',
        );
        await parseJsonResponse(
          await fetch(presign.upload_url, {
            method: presign.method ?? 'PUT',
            headers: presign.headers ?? { 'Content-Type': file.type || 'application/octet-stream' },
            body: file,
          }),
          'Unable to upload video',
        ).catch((error) => {
          // Some object stores return an empty response body for a successful PUT.
          if (String(error.message).includes('Unexpected end of JSON input')) return null;
          throw error;
        });
        return parseJsonResponse(
          await fetch(joinUrl(baseUrl, '/v1/jobs'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ upload_ref: presign.upload_ref }),
          }),
          'Unable to create job',
        );
      }
      return parseJsonResponse(
        await fetch(joinUrl(baseUrl, '/v1/jobs'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(input.upload_ref ? { upload_ref: input.upload_ref } : { source_url: input.source_url }),
        }),
        'Unable to create job',
      );
    },
    async *pollJob(jobId) {
      while (true) {
        const status = await parseJsonResponse(await fetch(joinUrl(baseUrl, `/v1/jobs/${jobId}`)), 'Unable to poll job');
        yield status;
        if (status.stage === 'complete') return;
        if (status.stage === 'failed') throw new Error(status.error ?? 'Job failed');
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    },
    async getResult(jobId) {
      return validateMeshResult(await parseJsonResponse(await fetch(joinUrl(baseUrl, `/v1/jobs/${jobId}/result`)), 'Unable to load result'));
    },
  };
}

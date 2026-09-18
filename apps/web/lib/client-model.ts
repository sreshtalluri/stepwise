export type Vec3 = [number, number, number];
export type Matrix4RowMajor = [number, number, number, number, number, number, number, number, number, number, number, number, number, number, number, number];

export type MeshResult = {
  schema_version: 'mesh-result-v1';
  video: { source_url: string; playback_url: string; duration_seconds: number; fps: number; dimensions: { width: number; height: number } };
  people: Person[];
  frames: Frame[];
  analysis: {
    beats: Array<{ timestamp_seconds: number; strength: number }>;
    difficulty: { overall_score: number; timeline: Array<{ timestamp_seconds: number; score: number }>; body_parts: Record<string, number> };
    foot_contacts: Array<{ track_id: string; foot: string; timestamp_seconds: number; contact: string; confidence: number }>;
    path_trails: Array<{ track_id: string; joint_name: string; points: Array<{ timestamp_seconds: number; position: Vec3 }> }>;
    step_segments: Array<{ label: string; start_seconds: number; end_seconds: number; difficulty: number; primary_body_part: string }>;
  };
  assets: { mesh_asset_urls: Array<{ track_id: string; url: string; content_type: string }>; glb_url?: string; debug_overlay_urls: string[] };
  model_report: { warnings: string[]; license_flags: Array<{ component: string; license: string; commercial_use: string; note: string }> };
};

export type Person = {
  track_id: string;
  color: string;
  confidence: number;
  visible_frame_ranges: number[][];
  primary_dancer_score: number;
  mesh_asset: MeshAsset | null;
  error?: string | null;
};

export type MeshAsset = {
  asset_id: string;
  format: 'inline-rest-mesh-v1';
  vertices: Vec3[];
  normals: Vec3[];
  faces: Array<[number, number, number]>;
  skin_weights: Array<{ joints: number[]; weights: number[] }>;
  joint_hierarchy: Array<{ name: string; parent_index: number | null; rest_position: Vec3 }>;
  inverse_bind_matrices: Matrix4RowMajor[];
  shape_parameters: { height_m: number; shoulder_width_m: number; hip_width_m: number; body_shape_coefficients: number[] };
  source_model: string;
};

export type Frame = { frame_index: number; timestamp_seconds: number; people: PersonFrame[] };
export type PersonFrame = { track_id: string; bbox: [number, number, number, number]; keypoints_2d: Array<{ name: string; position: [number, number]; confidence: number }>; joints_3d: Array<{ name: string; position: Vec3; rotation: [number, number, number, number]; confidence: number }>; pose_params: number[]; global_transform: { translation: Vec3; rotation: [number, number, number, number]; scale: Vec3 }; visibility: number; tracking_confidence: number };
export type JobStatus = { job_id: string; stage: string; progress: number; people_detected: number; error?: string | null };
export type CreateJobInput = { source_url?: string; upload_ref?: string; video_file?: File };

export const JOB_STAGES = ['queued', 'downloading', 'detecting', 'tracking', 'meshing', 'skinning', 'smoothing', 'analyzing', 'packaging', 'complete'] as const;

export function validateMeshResult(result: MeshResult): MeshResult {
  if (result.schema_version !== 'mesh-result-v1') throw new Error('Unsupported mesh result schema');
  for (const person of result.people) {
    if (person.mesh_asset && person.mesh_asset.vertices.length !== person.mesh_asset.skin_weights.length) {
      throw new Error(`Skin weights mismatch for ${person.track_id}`);
    }
  }
  return result;
}


export function transformPoint(matrix: Matrix4RowMajor, point: Vec3): Vec3 {
  const [x, y, z] = point;
  return [matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3], matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7], matrix[8] * x + matrix[9] * y + matrix[10] * z + matrix[11]];
}

export function applyLinearBlendSkinning(vertices: Vec3[], skinWeights: MeshAsset['skin_weights'], jointMatrices: Matrix4RowMajor[]): Vec3[] {
  return vertices.map((vertex, index) => {
    const row = skinWeights[index] ?? { joints: [0], weights: [1] };
    const output: Vec3 = [0, 0, 0];
    row.joints.forEach((jointIndex, weightIndex) => {
      const weight = row.weights[weightIndex] ?? 0;
      const matrix = jointMatrices[jointIndex] ?? jointMatrices[0];
      const transformed = transformPoint(matrix, vertex);
      output[0] += transformed[0] * weight;
      output[1] += transformed[1] * weight;
      output[2] += transformed[2] * weight;
    });
    return output;
  });
}

export function computeVisiblePeople(result: MeshResult, selectedTrackId: string): Person[] {
  const meshPeople = result.people.filter((person) => person.mesh_asset);
  if (selectedTrackId === 'all') return meshPeople;
  if (selectedTrackId === 'primary') return [...meshPeople].sort((a, b) => b.primary_dancer_score - a.primary_dancer_score).slice(0, 1);
  return meshPeople.filter((person) => person.track_id === selectedTrackId);
}

export function jointMatricesForPose(personFrame: PersonFrame | undefined, jointHierarchy: MeshAsset['joint_hierarchy'], inverseBindMatrices: Matrix4RowMajor[], mirror: boolean): Matrix4RowMajor[] {
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
    ] as Matrix4RowMajor;
  });
}

export function createMockMeshApiClient(result: MeshResult) {
  return {
    async createJob(input: CreateJobInput): Promise<JobStatus> {
      if (!input.source_url && !input.upload_ref && !input.video_file) throw new Error('Paste a link or upload a video.');
      return { job_id: `job-${Date.now()}`, stage: 'queued', progress: 0, people_detected: 0 };
    },
    async pollJob(jobId: string, onStatus: (status: JobStatus) => void) {
      const stages = JOB_STAGES.slice(1);
      for (let index = 0; index < stages.length; index += 1) {
        await new Promise((resolve) => setTimeout(resolve, 140));
        onStatus({ job_id: jobId, stage: stages[index], progress: stages[index] === 'complete' ? 100 : Math.round(((index + 1) / stages.length) * 95), people_detected: index >= 2 ? result.people.length : 0 });
      }
    },
    async getResult() {
      return validateMeshResult(result);
    },
  };
}

async function parseJsonResponse<T>(response: Response, fallbackMessage: string): Promise<T> {
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
  return response.json() as Promise<T>;
}

async function assertOk(response: Response, fallbackMessage: string): Promise<void> {
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
}

function joinUrl(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/$/, '')}${path}`;
}

type UploadPresignResponse = {
  method: 'PUT';
  upload_url: string;
  upload_ref: string;
  object_key: string;
  headers: Record<string, string>;
  expires_in_seconds: number;
};

export function createMeshApiClient({ baseUrl, fallbackResult }: { baseUrl?: string; fallbackResult: MeshResult }) {
  if (!baseUrl) return createMockMeshApiClient(fallbackResult);
  return {
    async createJob(input: CreateJobInput): Promise<JobStatus> {
      if (!input.source_url && !input.upload_ref && !input.video_file) throw new Error('Paste a link or upload a video.');
      if (input.video_file) {
        const presign = await parseJsonResponse<UploadPresignResponse>(
          await fetch(joinUrl(baseUrl, '/v1/uploads/presign'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filename: input.video_file.name,
              content_type: input.video_file.type || 'application/octet-stream',
              content_length: input.video_file.size,
            }),
          }),
          'Unable to prepare upload',
        );
        await assertOk(
          await fetch(presign.upload_url, {
            method: presign.method,
            headers: presign.headers,
            body: input.video_file,
          }),
          'Unable to upload video',
        );
        return parseJsonResponse<JobStatus>(
          await fetch(joinUrl(baseUrl, '/v1/jobs'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ upload_ref: presign.upload_ref }),
          }),
          'Unable to create job',
        );
      }
      return parseJsonResponse<JobStatus>(
        await fetch(joinUrl(baseUrl, '/v1/jobs'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(input.upload_ref ? { upload_ref: input.upload_ref } : { source_url: input.source_url }),
        }),
        'Unable to create job',
      );
    },
    async pollJob(jobId: string, onStatus: (status: JobStatus) => void) {
      for (;;) {
        const status = await parseJsonResponse<JobStatus>(await fetch(joinUrl(baseUrl, `/v1/jobs/${jobId}`)), 'Unable to poll job');
        onStatus(status);
        if (status.stage === 'complete') return;
        if (status.stage === 'failed') throw new Error(status.error ?? 'Job failed');
        await new Promise((resolve) => setTimeout(resolve, 1200));
      }
    },
    async getResult(jobId: string) {
      return validateMeshResult(await parseJsonResponse<MeshResult>(await fetch(joinUrl(baseUrl, `/v1/jobs/${jobId}/result`)), 'Unable to load result'));
    },
  };
}

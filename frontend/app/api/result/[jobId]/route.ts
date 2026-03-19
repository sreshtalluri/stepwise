import { NextRequest, NextResponse } from "next/server";

const PIPELINE_URL = process.env.PIPELINE_URL || "http://localhost:8000";
const USE_MOCK = process.env.USE_MOCK === "true";

/**
 * Transform the pipeline's StepwiseResult schema into the frontend's expected format.
 *
 * Pipeline produces: body_poses, hand_states, foot_contacts as separate arrays,
 *   duration_seconds, difficulty: { overall, per_frame }
 *
 * Frontend expects: frames (with joints as Record + inline hands/feet),
 *   duration, difficulty as segments array
 */
function transformResult(pipeline: Record<string, unknown>): Record<string, unknown> {
  const bodyPoses = pipeline.body_poses as Array<{
    frame: number;
    timestamp: number;
    joints: Array<{ name: string; x: number; y: number; z: number }>;
  }>;

  const handStates = pipeline.hand_states as Array<{
    frame: number;
    timestamp: number;
    left: { detected: boolean; gesture: string; confidence: number };
    right: { detected: boolean; gesture: string; confidence: number };
  }>;

  const footContacts = pipeline.foot_contacts as Array<{
    frame: number;
    timestamp: number;
    left: { contact: string };
    right: { contact: string };
  }>;

  // Build a lookup by frame index for hands and feet
  const handsByFrame = new Map<number, typeof handStates[0]>();
  for (const h of handStates || []) {
    handsByFrame.set(h.frame, h);
  }

  const feetByFrame = new Map<number, typeof footContacts[0]>();
  for (const f of footContacts || []) {
    feetByFrame.set(f.frame, f);
  }

  // Map gesture names: pipeline uses "open"/"closed"/"pointing"/"peace"/"unknown"/"none"
  // Frontend uses "fist"/"open"/"spread"/"pointing"
  function mapGesture(gesture: string): string {
    switch (gesture) {
      case "closed": return "fist";
      case "open": return "open";
      case "peace": return "spread";
      case "pointing": return "pointing";
      default: return "fist";
    }
  }

  // Transform frames
  const frames = (bodyPoses || []).map((pose) => {
    // Convert joints array to Record<name, {x,y,z,confidence}>
    const joints: Record<string, { x: number; y: number; z: number; confidence: number }> = {};
    for (const j of pose.joints) {
      joints[j.name] = { x: j.x, y: j.y, z: j.z, confidence: 1.0 };
    }

    const frame: Record<string, unknown> = {
      timestamp: pose.timestamp,
      joints,
    };

    // Inline hand annotations
    const hand = handsByFrame.get(pose.frame);
    if (hand) {
      const hands = [];
      if (hand.left.detected) {
        hands.push({ joint: "left_hand", state: mapGesture(hand.left.gesture) });
      }
      if (hand.right.detected) {
        hands.push({ joint: "right_hand", state: mapGesture(hand.right.gesture) });
      }
      if (hands.length > 0) {
        frame.hands = hands;
      }
    }

    // Inline foot annotations
    const foot = feetByFrame.get(pose.frame);
    if (foot) {
      frame.feet = [
        { joint: "left_foot", state: foot.left.contact },
        { joint: "right_foot", state: foot.right.contact },
      ];
    }

    return frame;
  });

  // Transform difficulty: pipeline { overall, per_frame: [{frame, score}] } -> frontend [{start, end, score}]
  const pipelineDifficulty = pipeline.difficulty as {
    overall: number;
    per_frame: Array<{ frame: number; score: number }>;
  };
  const fps = pipeline.fps as number;
  const durationSeconds = pipeline.duration_seconds as number;
  const difficulty: Array<{ start: number; end: number; score: number }> = [];

  if (pipelineDifficulty?.per_frame?.length) {
    // Group per-frame difficulty into segments of roughly equal score
    const perFrame = pipelineDifficulty.per_frame;
    const segmentSize = Math.max(1, Math.floor(perFrame.length / 3));

    for (let i = 0; i < perFrame.length; i += segmentSize) {
      const segment = perFrame.slice(i, i + segmentSize);
      const avgScore = segment.reduce((s, f) => s + f.score, 0) / segment.length;
      const startTime = segment[0].frame / fps;
      const endTime = (segment[segment.length - 1].frame + 1) / fps;
      difficulty.push({
        start: Math.round(startTime * 100) / 100,
        end: Math.min(Math.round(endTime * 100) / 100, durationSeconds),
        score: Math.round(avgScore * 100) / 100,
      });
    }
  }

  return {
    version: pipeline.version,
    source_url: pipeline.source_url,
    duration: durationSeconds,
    fps,
    frames,
    beats: pipeline.beats,
    difficulty,
    metadata: {
      platform: "unknown",
    },
  };
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  const { jobId } = params;

  if (!jobId) {
    return NextResponse.json({ error: "Job ID is required" }, { status: 400 });
  }

  // Mock mode: serve the fixture directly
  if (USE_MOCK) {
    return NextResponse.redirect(new URL("/fixtures/sample-result.json", _request.url));
  }

  // Check server-side result cache (set by /api/process + /api/status)
  const results = (globalThis as any).__stepwise_results || {};
  const cachedResult = results[jobId];

  if (cachedResult) {
    // Transform pipeline format to frontend format
    const frontendResult = transformResult(cachedResult);
    return NextResponse.json(frontendResult);
  }

  // Fallback: check if the job has a result in the global jobs state
  const jobs = (globalThis as any).__stepwise_jobs || {};
  const job = jobs[jobId];

  if (job?.status === "complete" && job.result) {
    const frontendResult = transformResult(job.result);
    return NextResponse.json(frontendResult);
  }

  return NextResponse.json(
    { error: "Result not ready yet" },
    { status: 202 }
  );
}

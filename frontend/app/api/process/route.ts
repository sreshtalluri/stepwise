import { NextRequest, NextResponse } from "next/server";
import { v4 as uuidv4 } from "uuid";
import { registerMockJob } from "@/lib/mock-jobs";

const PIPELINE_URL = process.env.PIPELINE_URL || "http://localhost:8000";
const USE_MOCK = process.env.USE_MOCK === "true";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { url } = body;

    if (!url || typeof url !== "string") {
      return NextResponse.json(
        { error: "URL is required" },
        { status: 400 }
      );
    }

    // Mock mode: return a fake job ID immediately
    if (USE_MOCK) {
      const jobId = uuidv4();
      registerMockJob(jobId);
      return NextResponse.json({ jobId });
    }

    // Call the pipeline's sync endpoint — processes the video and returns the result
    // This is necessary because Modal is serverless and in-memory job tracking
    // doesn't persist across container instances.
    const jobId = uuidv4();
    registerMockJob(jobId); // Register so status endpoint can track it

    // Start processing in the background via the sync endpoint
    // The frontend will poll /api/status which checks a simple flag
    const processingPromise = fetch(`${PIPELINE_URL}/process/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }).then(async (res) => {
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: "Pipeline error" }));
        // Store error in global state for status endpoint
        (globalThis as any).__stepwise_jobs = (globalThis as any).__stepwise_jobs || {};
        (globalThis as any).__stepwise_jobs[jobId] = { status: "error", error: error.detail || "Processing failed" };
        return;
      }
      const result = await res.json();
      (globalThis as any).__stepwise_jobs = (globalThis as any).__stepwise_jobs || {};
      (globalThis as any).__stepwise_jobs[jobId] = { status: "complete", result };
    }).catch((err) => {
      (globalThis as any).__stepwise_jobs = (globalThis as any).__stepwise_jobs || {};
      (globalThis as any).__stepwise_jobs[jobId] = { status: "error", error: `Pipeline connection failed: ${err.message}` };
    });

    // Don't await — return job ID immediately so the user sees processing state
    void processingPromise;

    return NextResponse.json({ jobId });
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 }
    );
  }
}

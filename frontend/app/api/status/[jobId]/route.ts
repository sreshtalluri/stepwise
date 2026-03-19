import { NextRequest, NextResponse } from "next/server";
import { PROCESSING_STEPS } from "@/lib/constants";
import { isMockJobRegistered } from "@/lib/mock-jobs";

const PIPELINE_URL = process.env.PIPELINE_URL || "http://localhost:8000";
const USE_MOCK = process.env.USE_MOCK === "true";

// ---------------------------------------------------------------------------
// Mock mode state
// ---------------------------------------------------------------------------
const jobCreationTimes = new Map<string, number>();

function getJobAge(jobId: string): number {
  if (!jobCreationTimes.has(jobId)) {
    jobCreationTimes.set(jobId, Date.now());
  }
  return Date.now() - jobCreationTimes.get(jobId)!;
}

function mockStatus(jobId: string) {
  const age = getJobAge(jobId);
  const processingDuration = 5000;

  if (age < processingDuration) {
    const stepDuration = processingDuration / PROCESSING_STEPS.length;
    const stepIndex = Math.min(
      Math.floor(age / stepDuration),
      PROCESSING_STEPS.length - 1
    );

    return {
      status: "processing" as const,
      step: PROCESSING_STEPS[stepIndex],
    };
  }

  return {
    status: "complete" as const,
    result_url: "/fixtures/sample-result.json",
  };
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function GET(
  _request: NextRequest,
  { params }: { params: { jobId: string } }
) {
  const { jobId } = params;

  if (!jobId) {
    return NextResponse.json(
      { error: "Job ID is required" },
      { status: 400 }
    );
  }

  // Mock mode
  if (USE_MOCK) {
    if (!isMockJobRegistered(jobId)) {
      return NextResponse.json(
        { status: "error", error: "Job not found" },
        { status: 404 }
      );
    }
    return NextResponse.json(mockStatus(jobId));
  }

  // Check server-side job state (set by /api/process background fetch)
  const jobs = (globalThis as any).__stepwise_jobs || {};
  const job = jobs[jobId];

  if (!job) {
    // Job was registered (mock check passed) but not yet complete — still processing
    return NextResponse.json({
      status: "processing",
      step: "Processing video...",
    });
  }

  if (job.status === "complete") {
    // Store the result in a retrievable location and return a URL
    // Cache the result JSON for the result endpoint to serve
    (globalThis as any).__stepwise_results = (globalThis as any).__stepwise_results || {};
    (globalThis as any).__stepwise_results[jobId] = job.result;

    return NextResponse.json({
      status: "complete",
      result_url: `/api/result/${jobId}`,
    });
  }

  if (job.status === "error") {
    return NextResponse.json({
      status: "error",
      error_message: job.error || "Processing failed",
    });
  }

  return NextResponse.json({
    status: "processing",
    step: "Processing video...",
  });
}

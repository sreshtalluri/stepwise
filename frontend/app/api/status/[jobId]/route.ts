import { NextRequest, NextResponse } from "next/server";
import { PROCESSING_STEPS } from "@/lib/constants";

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
    return NextResponse.json(mockStatus(jobId));
  }

  // Call the real pipeline status endpoint
  try {
    const pipelineRes = await fetch(`${PIPELINE_URL}/status/${jobId}`);

    if (!pipelineRes.ok) {
      if (pipelineRes.status === 404) {
        return NextResponse.json(
          { error: "Job not found" },
          { status: 404 }
        );
      }
      return NextResponse.json(
        { error: "Failed to fetch job status" },
        { status: pipelineRes.status }
      );
    }

    const data = await pipelineRes.json();

    // Map pipeline status to frontend format
    if (data.status === "processing") {
      return NextResponse.json({
        status: "processing",
        step: data.step || "Processing...",
      });
    }

    if (data.status === "complete") {
      // Return the proxy URL so the frontend gets data in the expected format
      return NextResponse.json({
        status: "complete",
        result_url: `/api/result/${jobId}`,
      });
    }

    if (data.status === "error") {
      return NextResponse.json({
        status: "error",
        error_message: data.error || "Processing failed",
      });
    }

    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: "Failed to connect to pipeline" },
      { status: 502 }
    );
  }
}

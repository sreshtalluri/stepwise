import { NextRequest, NextResponse } from "next/server";
import { PROCESSING_STEPS } from "@/lib/constants";

// Shared job store - since we can't import from another route in Next.js edge runtime,
// we use a module-level map that gets populated via the process route.
// In production, this would be a database.
const jobCreationTimes = new Map<string, number>();

// Register job creation time (called from a shared mechanism)
function getJobAge(jobId: string): number {
  if (!jobCreationTimes.has(jobId)) {
    // First time we've seen this job - start tracking now
    jobCreationTimes.set(jobId, Date.now());
  }
  return Date.now() - jobCreationTimes.get(jobId)!;
}

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

  const age = getJobAge(jobId);
  const processingDuration = 5000; // 5 seconds mock processing

  if (age < processingDuration) {
    // Calculate which step we're on
    const stepDuration = processingDuration / PROCESSING_STEPS.length;
    const stepIndex = Math.min(
      Math.floor(age / stepDuration),
      PROCESSING_STEPS.length - 1
    );

    return NextResponse.json({
      status: "processing",
      step: PROCESSING_STEPS[stepIndex],
    });
  }

  // Processing complete
  return NextResponse.json({
    status: "complete",
    result_url: "/fixtures/sample-result.json",
  });
}

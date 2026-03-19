import { NextRequest, NextResponse } from "next/server";
import { v4 as uuidv4 } from "uuid";

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
      return NextResponse.json({ jobId });
    }

    // Call the real pipeline
    const pipelineRes = await fetch(`${PIPELINE_URL}/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    if (!pipelineRes.ok) {
      const error = await pipelineRes.json().catch(() => ({ detail: "Pipeline error" }));
      return NextResponse.json(
        { error: error.detail || "Pipeline processing failed" },
        { status: pipelineRes.status }
      );
    }

    const data = await pipelineRes.json();
    return NextResponse.json({ jobId: data.job_id });
  } catch {
    return NextResponse.json(
      { error: "Invalid request body" },
      { status: 400 }
    );
  }
}

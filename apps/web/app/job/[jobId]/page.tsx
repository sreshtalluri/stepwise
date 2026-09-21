"use client";

import { use } from "react";
import ProcessingScreen from "../../../components/ProcessingScreen";

export default function JobPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  return <ProcessingScreen jobId={jobId} />;
}

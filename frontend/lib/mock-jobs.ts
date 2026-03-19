// In-memory registry of mock job IDs created via /api/process.
// Shared across API routes within the same server process.
const createdJobIds = new Set<string>();

export function registerMockJob(jobId: string): void {
  createdJobIds.add(jobId);
}

export function isMockJobRegistered(jobId: string): boolean {
  return createdJobIds.has(jobId);
}

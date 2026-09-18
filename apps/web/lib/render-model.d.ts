export type MeshResult = any;
export const JOB_STAGES: string[];
export function applyLinearBlendSkinning(vertices: number[][], skinWeights: Array<{ joints: number[]; weights: number[] }>, jointMatrices: number[][]): number[][];
export function validateMeshResult(result: MeshResult): MeshResult;
export function loadFixtureResult(name: string): MeshResult;
export function computeVisiblePeople(result: MeshResult, selectedTrackId: string): any[];
export function jointMatricesForPose(personFrame: any, jointHierarchy: any[], inverseBindMatrices: number[][], mirror: boolean): number[][];
export function createMockMeshApiClient(result: MeshResult): any;

"use client";

import { useRef, useEffect } from "react";
import { PoseFrame } from "@/lib/types";
import { BONE_CONNECTIONS } from "@/lib/constants";

const PIPELINE_SCALE = 1.8;
const JOINT_RADIUS = 4;
const BONE_WIDTH = 2;
const JOINT_COLOR = "#00d4ff";
const BONE_COLOR = "rgba(0, 212, 255, 0.8)";
const GLOW_COLOR = "rgba(0, 212, 255, 0.3)";

interface GhostSkeletonCanvasProps {
  frames: PoseFrame[];
  currentFrame: number;
  width: number;
  height: number;
}

/** Convert pipeline coordinates back to pixel positions */
function toPixel(
  jointX: number,
  jointY: number,
  canvasW: number,
  canvasH: number
): [number, number] {
  const normX = jointX / PIPELINE_SCALE + 0.5;
  const normY = 1.0 - jointY / PIPELINE_SCALE;
  return [normX * canvasW, normY * canvasH];
}

export function GhostSkeletonCanvas({
  frames,
  currentFrame,
  width,
  height,
}: GhostSkeletonCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const frame = frames[currentFrame] || frames[0];
    if (!frame) return;

    // Debug: log coordinate ranges on first frame
    if (currentFrame === 0) {
      const allJoints = Object.entries(frame.joints);
      const ys = allJoints.map(([, j]) => j.y);
      const xs = allJoints.map(([, j]) => j.x);
      console.log(`[Ghost Debug] Y:[${Math.min(...ys).toFixed(3)}, ${Math.max(...ys).toFixed(3)}] X:[${Math.min(...xs).toFixed(3)}, ${Math.max(...xs).toFixed(3)}] canvas:${width}x${height}`);
      console.log(`[Ghost Debug] Head Y:${frame.joints.head?.y.toFixed(3)} Pelvis Y:${frame.joints.pelvis?.y.toFixed(3)} Foot Y:${frame.joints.left_foot?.y.toFixed(3)}`);
    }

    // Handle high-DPI displays
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);

    // Clear
    ctx.clearRect(0, 0, width, height);

    const joints = frame.joints;

    // Draw bones
    ctx.strokeStyle = BONE_COLOR;
    ctx.lineWidth = BONE_WIDTH;
    ctx.lineCap = "round";
    for (const [a, b] of BONE_CONNECTIONS) {
      const jA = joints[a as keyof typeof joints];
      const jB = joints[b as keyof typeof joints];
      if (!jA || !jB) continue;

      const [ax, ay] = toPixel(jA.x, jA.y, width, height);
      const [bx, by] = toPixel(jB.x, jB.y, width, height);

      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
    }

    // Draw glow behind joints
    for (const joint of Object.values(joints)) {
      const [px, py] = toPixel(joint.x, joint.y, width, height);
      ctx.beginPath();
      ctx.arc(px, py, JOINT_RADIUS + 3, 0, Math.PI * 2);
      ctx.fillStyle = GLOW_COLOR;
      ctx.fill();
    }

    // Draw joints
    for (const joint of Object.values(joints)) {
      const [px, py] = toPixel(joint.x, joint.y, width, height);
      ctx.beginPath();
      ctx.arc(px, py, JOINT_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = JOINT_COLOR;
      ctx.fill();
    }
  }, [frames, currentFrame, width, height]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width, height, display: "block" }}
    />
  );
}

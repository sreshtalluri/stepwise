'use client';

import dynamic from 'next/dynamic';
import fixture from '@/public/fixtures/multi-person.json';
import { createMeshApiClient, computeVisiblePeople, validateMeshResult, type JobStatus, type MeshResult, type Person } from '@/lib/client-model';
import { useMemo, useState } from 'react';

const MeshCanvas = dynamic(() => import('./MeshCanvas'), { ssr: false, loading: () => <div className="flex h-full items-center justify-center text-cyan-300">Loading WebGL mesh surface…</div> });

type Screen = 'landing' | 'processing' | 'viewer';
type LayoutMode = 'side-by-side' | 'ghost' | 'front' | 'back' | 'formation';

const fixtureResult = validateMeshResult(fixture as unknown as MeshResult);
const api = createMeshApiClient({ baseUrl: process.env.NEXT_PUBLIC_MESH_API_URL, fallbackResult: fixtureResult });

function Header() {
  return (
    <header className="relative z-10 flex items-center justify-between px-6 py-5 md:px-10">
      <div className="font-display text-2xl font-bold tracking-tight">stepwise</div>
      <nav className="hidden gap-8 text-sm text-[#888] md:flex">
        <span>Mesh API</span><span>Model licenses</span><span>Viewer</span>
      </nav>
      <a href="#upload" className="rounded-button border border-accent/50 px-4 py-2 font-mono text-xs uppercase tracking-widest text-accent hover:bg-accent hover:text-black">Start</a>
    </header>
  );
}

export default function StepwiseMeshApp() {
  const [screen, setScreen] = useState<Screen>('landing');
  const [sourceUrl, setSourceUrl] = useState('https://www.youtube.com/watch?v=two-person-dance');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus>({ job_id: '', stage: 'queued', progress: 0, people_detected: 0 });
  const [meshResult, setMeshResult] = useState<MeshResult>(fixtureResult);
  const [selected, setSelected] = useState('all');
  const [layout, setLayout] = useState<LayoutMode>('side-by-side');
  const [mirror, setMirror] = useState(false);
  const [xray, setXray] = useState(false);
  const [orbit, setOrbit] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [loop, setLoop] = useState<[number, number]>([0, 1.2]);
  const [frameIndex, setFrameIndex] = useState(0);

  const visiblePeople = useMemo(() => computeVisiblePeople(meshResult, selected), [meshResult, selected]);
  const primary = useMemo(() => [...meshResult.people].sort((a, b) => b.primary_dancer_score - a.primary_dancer_score)[0], [meshResult]);

  async function submit() {
    setError(null);
    try {
      setWarning('Stepwise will probe duration, fps, and resolution from the actual video before meshing.');
      setScreen('processing');
      const job = await api.createJob(uploadFile ? { video_file: uploadFile, upload_ref: uploadFile.name } : { source_url: sourceUrl });
      setStatus(job);
      await api.pollJob(job.job_id, setStatus);
      const completedResult = await api.getResult(job.job_id);
      setMeshResult(completedResult);
      setFrameIndex(0);
      setSelected('all');
      setScreen('viewer');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create job');
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden">
      <Header />
      {screen === 'landing' && <Landing sourceUrl={sourceUrl} setSourceUrl={setSourceUrl} uploadFile={uploadFile} setUploadFile={setUploadFile} error={error} warning={warning} onSubmit={submit} />}
      {screen === 'processing' && <Processing status={status} warning={warning} />}
      {screen === 'viewer' && <Viewer sourceUrl={meshResult.video.source_url || sourceUrl} result={meshResult} people={visiblePeople} primary={primary} selected={selected} setSelected={setSelected} layout={layout} setLayout={setLayout} mirror={mirror} setMirror={setMirror} xray={xray} setXray={setXray} orbit={orbit} setOrbit={setOrbit} speed={speed} setSpeed={setSpeed} loop={loop} setLoop={setLoop} frameIndex={frameIndex} setFrameIndex={setFrameIndex} />}
    </main>
  );
}

function Landing(props: { sourceUrl: string; setSourceUrl: (value: string) => void; uploadFile: File | null; setUploadFile: (value: File | null) => void; error: string | null; warning: string | null; onSubmit: () => void }) {
  return (
    <section id="upload" className="relative z-10 mx-auto grid max-w-7xl gap-10 px-6 py-16 md:grid-cols-[1.05fr_.95fr] md:px-10 md:py-24">
      <div>
        <h1 className="font-display text-5xl font-bold leading-[.92] tracking-[-.06em] md:text-7xl">Full-body mesh recovery for every dancer in the frame.</h1>
        <p className="mt-7 max-w-2xl text-lg leading-8 text-[#aaa]">Paste a YouTube, TikTok, Instagram, or direct video link — or upload an already-downloaded clip. The API probes duration and resolution from the video, then detects people, tracks identities, and generates stylized skinned body surfaces.</p>
        <div className="mt-10 mesh-panel p-4 md:p-5">
          <input aria-label="YouTube, TikTok, Instagram, or direct video URL" value={props.sourceUrl} onChange={(event) => props.setSourceUrl(event.target.value)} placeholder="Paste YouTube, TikTok, Instagram, or direct video URL" className="w-full rounded-input border border-[#222] bg-black/60 px-4 py-4 text-base outline-none ring-accent/40 focus:ring-2" />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="rounded-button border border-[#333] px-4 py-3 text-sm text-[#aaa] hover:border-accent/50">Upload downloaded video<input type="file" accept="video/*" className="hidden" onChange={(event) => props.setUploadFile(event.target.files?.[0] ?? null)} /></label>
            {props.uploadFile && <span className="font-mono text-xs text-accent">{props.uploadFile.name}</span>}
            <span className="ml-auto font-mono text-xs text-[#888]">Duration is detected automatically</span>
          </div>
          <button onClick={props.onSubmit} className="mt-5 w-full rounded-button bg-accent px-5 py-4 font-mono text-sm font-semibold uppercase tracking-widest text-black cyan-glow">Generate mesh result</button>
          {props.error && <p className="mt-3 border-l-2 border-error bg-error/10 p-3 text-sm text-error">{props.error}</p>}
          {props.warning && <p className="mt-3 border-l-2 border-warning bg-warning/10 p-3 text-sm text-warning">{props.warning}</p>}
        </div>
      </div>
      <div className="mesh-panel min-h-[540px] overflow-hidden p-5">
        <div className="hud-label">link → video ingest → mesh</div>
        <div className="mt-4 grid grid-cols-2 gap-3">
          {['Link download/probe', 'YOLO detector', 'ID tracker', 'Humanoid mesh'].map((label, index) => <div key={label} className="rounded-lg border border-[#222] bg-black/35 p-4"><div className="font-mono text-2xl text-accent">0{index + 1}</div><div className="mt-2 text-sm text-[#aaa]">{label}</div></div>)}
        </div>
        <div className="mt-6 rounded-xl border border-accent/20 bg-accent/5 p-5">
          <div className="hud-label">Body surfaces, not stick figures</div>
          <div className="mt-5 flex h-72 items-end justify-center gap-10">
            {fixtureResult.people.slice(0, 2).map((person) => <MiniBody key={person.track_id} person={person} />)}
          </div>
        </div>
      </div>
    </section>
  );
}

function MiniBody({ person }: { person: Person }) {
  return <div className="relative flex h-56 w-24 items-center justify-center"><div style={{ background: person.color }} className="absolute h-48 w-16 rounded-[48%] opacity-70 blur-sm" /><div className="absolute h-52 w-20 rounded-[48%] border border-white/25 bg-black/60" /><div className="relative font-mono text-[10px] text-white">{person.track_id.replace('person-', '')}</div></div>;
}

function Processing({ status, warning }: { status: JobStatus; warning: string | null }) {
  const stages = ['queued', 'downloading', 'detecting', 'tracking', 'meshing', 'skinning', 'smoothing', 'analyzing', 'packaging', 'complete'];
  const current = stages.indexOf(status.stage);
  return (
    <section className="relative z-10 mx-auto max-w-4xl px-6 py-20">
      <div className="mesh-panel p-8">
        <div className="hud-label">Processing job</div>
        <h2 className="mt-4 font-display text-5xl font-bold">{status.stage}</h2>
        <div className="mt-8 h-3 overflow-hidden rounded-full bg-[#222]"><div style={{ width: `${status.progress}%` }} className="h-full bg-accent cyan-glow transition-all" /></div>
        <div className="mt-8 grid gap-3 md:grid-cols-2">
          {stages.map((stage, index) => <div key={stage} className={`rounded-lg border p-4 font-mono text-xs uppercase tracking-widest ${index <= current ? 'border-accent/50 bg-accent/10 text-accent' : 'border-[#222] text-[#555]'}`}>{stage}</div>)}
        </div>
        <div className="mt-6 flex gap-4 text-sm text-[#aaa]"><span>People detected: {status.people_detected}</span><span>GPU pipeline ETA: {Math.max(0, 100 - status.progress)}%</span></div>
        {warning && <p className="mt-4 border-l-2 border-warning bg-warning/10 p-3 text-sm text-warning">{warning}</p>}
      </div>
    </section>
  );
}

function Viewer(props: { sourceUrl: string; result: MeshResult; people: Person[]; primary: Person; selected: string; setSelected: (value: string) => void; layout: LayoutMode; setLayout: (value: LayoutMode) => void; mirror: boolean; setMirror: (value: boolean) => void; xray: boolean; setXray: (value: boolean) => void; orbit: boolean; setOrbit: (value: boolean) => void; speed: number; setSpeed: (value: number) => void; loop: [number, number]; setLoop: (value: [number, number]) => void; frameIndex: number; setFrameIndex: (value: number) => void }) {
  const frame = props.result.frames[props.frameIndex % props.result.frames.length];
  return (
    <section className="relative z-10 grid min-h-[calc(100vh-84px)] gap-3 px-3 pb-3 lg:grid-cols-[280px_1fr_320px]">
      <aside className="mesh-panel p-4">
        <div className="hud-label">People</div>
        <button onClick={() => props.setSelected('primary')} className={`mt-4 w-full rounded px-3 py-2 text-left text-sm ${props.selected === 'primary' ? 'bg-accent text-black' : 'bg-black/40 text-[#aaa]'}`}>Auto-focus primary ({props.primary.track_id})</button>
        <button onClick={() => props.setSelected('all')} className={`mt-2 w-full rounded px-3 py-2 text-left text-sm ${props.selected === 'all' ? 'bg-accent text-black' : 'bg-black/40 text-[#aaa]'}`}>All mesh surfaces</button>
        {props.result.people.map((person) => <button key={person.track_id} onClick={() => props.setSelected(person.track_id)} className={`mt-2 flex w-full items-center justify-between rounded px-3 py-2 text-left text-sm ${props.selected === person.track_id ? 'bg-accent text-black' : 'bg-black/40 text-[#aaa]'}`}><span>{person.track_id}</span><span style={{ color: person.color }}>●</span></button>)}
        <div className="mt-6 hud-label">View modes</div>
        {(['side-by-side', 'ghost', 'front', 'back', 'formation'] as LayoutMode[]).map((mode) => <button key={mode} onClick={() => props.setLayout(mode)} className={`mt-2 w-full rounded px-3 py-2 text-left font-mono text-xs uppercase ${props.layout === mode ? 'bg-accent text-black' : 'bg-black/40 text-[#aaa]'}`}>{mode}</button>)}
        <div className="mt-6 grid grid-cols-2 gap-2">{[['Mirror', props.mirror, props.setMirror], ['X-ray', props.xray, props.setXray], ['Freeze/orbit', props.orbit, props.setOrbit]] .map(([label, value, setter]) => <button key={label as string} onClick={() => (setter as (v: boolean) => void)(!(value as boolean))} className={`rounded px-3 py-2 font-mono text-xs ${value ? 'bg-accent text-black' : 'bg-black/40 text-[#aaa]'}`}>{label as string}</button>)}</div>
      </aside>
      <div className={`grid gap-3 ${props.layout === 'side-by-side' ? 'lg:grid-cols-2' : 'grid-cols-1'}`}>
        {props.layout !== 'front' && <VideoPanel sourceUrl={props.sourceUrl} ghost={props.layout === 'ghost'} />}
        <div className="mesh-panel relative min-h-[520px] overflow-hidden"><div className="absolute left-4 top-4 z-10 rounded bg-black/60 px-3 py-2 hud-label">Skinned mesh surface</div><MeshCanvas result={props.result} people={props.people} frameIndex={props.frameIndex} mirror={props.mirror || props.layout === 'back'} xray={props.xray} orbit={props.orbit} /></div>
        {props.layout === 'formation' && <Formation result={props.result} frameIndex={props.frameIndex} />}
      </div>
      <aside className="mesh-panel p-4">
        <div className="hud-label">Timeline</div>
        <input aria-label="Frame" type="range" min={0} max={props.result.frames.length - 1} value={props.frameIndex} onChange={(event) => props.setFrameIndex(Number(event.target.value))} className="mt-4 w-full accent-cyan-400" />
        <div className="mt-2 font-mono text-sm text-accent">{frame.timestamp_seconds.toFixed(3)}s · frame {frame.frame_index}</div>
        <div className="mt-5 grid grid-cols-4 gap-2">{[0.5, 1, 1.5, 2].map((value) => <button key={value} onClick={() => props.setSpeed(value)} className={`rounded px-2 py-2 font-mono text-xs ${props.speed === value ? 'bg-accent text-black' : 'bg-black/40 text-[#aaa]'}`}>{value}x</button>)}</div>
        <label className="mt-5 block text-sm text-[#aaa]">Loop end <input type="range" min={0.4} max={2} step={0.1} value={props.loop[1]} onChange={(event) => props.setLoop([0, Number(event.target.value)])} className="w-full accent-cyan-400" /></label>
        <Heatmap result={props.result} />
        <BodyParts result={props.result} />
        <StepMarkers result={props.result} />
        <PathTrails result={props.result} />
        <div className="mt-5 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">License review: {props.result.model_report.license_flags[0]?.license}</div>
      </aside>
    </section>
  );
}

function VideoPanel({ sourceUrl, ghost }: { sourceUrl: string; ghost: boolean }) {
  return <div className="mesh-panel relative min-h-[520px] overflow-hidden bg-black"><div className="absolute left-4 top-4 z-10 rounded bg-black/60 px-3 py-2 hud-label">Original video {ghost ? '+ ghost overlay' : ''}</div><div className="absolute inset-8 flex items-center justify-center rounded-xl border border-[#222] bg-[radial-gradient(circle,rgba(0,212,255,.18),transparent_42%)] text-center text-[#888]"><div><div className="font-mono text-xs">{sourceUrl}</div><div className="mt-4 text-6xl text-accent/50">▶</div></div></div>{ghost && <div className="absolute inset-8 rounded-xl border border-accent/60 bg-accent/10 mix-blend-screen" />}</div>;
}
function Heatmap({ result }: { result: MeshResult }) { return <div className="mt-6"><div className="hud-label">Difficulty heatmap</div><div className="mt-2 flex h-5 overflow-hidden rounded-full">{result.analysis.difficulty.timeline.map((item) => <div key={item.timestamp_seconds} style={{ flex: 1, background: `linear-gradient(90deg,#44ff88, ${item.score > .55 ? '#ffdd44' : '#44ff88'}, ${item.score > .66 ? '#ff4444' : '#ffdd44'})`, opacity: .35 + item.score * .65 }} />)}</div></div>; }
function BodyParts({ result }: { result: MeshResult }) { return <div className="mt-6"><div className="hud-label">Body-part heatmap</div>{Object.entries(result.analysis.difficulty.body_parts).map(([part, score]) => <div key={part} className="mt-2"><div className="flex justify-between text-sm text-[#aaa]"><span>{part}</span><span>{Math.round(score * 100)}%</span></div><div className="h-2 rounded bg-[#222]"><div style={{ width: `${score * 100}%` }} className="h-full rounded bg-accent" /></div></div>)}</div>; }
function StepMarkers({ result }: { result: MeshResult }) { return <div className="mt-6"><div className="hud-label">Step markers</div>{result.analysis.step_segments.map((step) => <div key={step.label} className="mt-2 rounded border border-[#222] bg-black/35 p-3"><div className="text-sm text-white">{step.label}</div><div className="font-mono text-xs text-[#888]">{step.start_seconds}s–{step.end_seconds}s · {step.primary_body_part}</div></div>)}</div>; }
function PathTrails({ result }: { result: MeshResult }) { return <div className="mt-6"><div className="hud-label">Hands / feet trails</div><div className="mt-2 grid grid-cols-2 gap-2">{result.analysis.path_trails.slice(0, 8).map((trail) => <div key={`${trail.track_id}-${trail.joint_name}`} className="rounded border border-[#222] bg-black/35 p-2 font-mono text-[10px] text-[#888]">{trail.joint_name} · {trail.points.length} pts</div>)}</div></div>; }
function Formation({ result, frameIndex }: { result: MeshResult; frameIndex: number }) { const frame = result.frames[frameIndex % result.frames.length]; return <div className="mesh-panel relative min-h-[220px] p-4"><div className="hud-label">Formation minimap</div><div className="relative mt-4 h-40 rounded-lg border border-[#222] bg-black/50">{frame.people.map((person) => <div key={person.track_id} style={{ left: `${(person.global_transform.translation[0] + .6) * 70}%`, top: `${40 + person.global_transform.translation[2] * 30}%`, background: result.people.find((p) => p.track_id === person.track_id)?.color }} className="absolute h-4 w-4 rounded-full shadow-[0_0_18px_currentColor]" />)}</div></div>; }

import ScanLive from "@/components/ScanLive";

// Dynamic scan view. The id comes from the route; all live data streams over
// SSE from the orchestrator (see components/ScanLive.tsx).
export default function ScanPage({ params }: { params: { id: string } }) {
  return <ScanLive id={params.id} />;
}

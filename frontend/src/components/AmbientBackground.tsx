// Ambient animated backdrop: slowly drifting blurred color orbs + a faint grid.
// Purely decorative, sits behind everything and ignores pointer events.
export default function AmbientBackground() {
  return (
    <div className="ambient" aria-hidden="true">
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
      <div className="ambient-grid" />
      <div className="ambient-vignette" />
    </div>
  );
}

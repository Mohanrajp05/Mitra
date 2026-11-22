export default function Loading({ label = 'Loading...', fullPage = false }) {
  return (
    <div className={fullPage ? 'loading loading-fullpage' : 'loading'} role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  )
}

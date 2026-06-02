// Reusable skeleton block — gray pulsing placeholder
export default function Skeleton({ className = '' }) {
  return <div className={`bg-gray-200 rounded-xl animate-pulse ${className}`} />
}

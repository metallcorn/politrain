import Spinner from './Spinner'

export default function Button({ children, variant = 'primary', loading, className = '', ...props }) {
  const base = 'flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed'
  const variants = {
    primary: 'bg-primary-800 text-white hover:bg-primary-700 active:bg-primary-900',
    secondary: 'bg-white text-primary-800 border border-primary-200 hover:bg-primary-50',
    ghost: 'text-gray-600 hover:bg-gray-100',
    danger: 'bg-red-600 text-white hover:bg-red-700',
    success: 'bg-green-600 text-white hover:bg-green-700',
  }
  return (
    <button className={`${base} ${variants[variant]} ${className}`} disabled={loading || props.disabled} {...props}>
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  )
}

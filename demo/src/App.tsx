import Counter from './Counter'

export default function App() {
  return (
    <div className="container">
      <h1>RepoMedic Demo App</h1>
      {/* BUG 1 (TypeScript build error): Passing string "0" to numeric initialCount */}
      <Counter initialCount="0" label="Active Counter" />
    </div>
  )
}

import { useState } from 'react'

export interface CounterProps {
  initialCount: number;
  label: string;
}

export default function Counter({ initialCount, label }: CounterProps) {
  const [count, setCount] = useState<number>(initialCount)

  // BUG 2 (Logic bug): Decrements instead of incrementing on button click
  const handleIncrement = () => {
    setCount(count - 1)
  }

  return (
    <div className="counter-box">
      <h2>{label}</h2>
      <div data-testid="count-value" className="count-display">
        Count: {count}
      </div>
      <button onClick={handleIncrement} className="increment-btn">
        Increment
      </button>
    </div>
  )
}

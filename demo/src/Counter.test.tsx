import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import Counter from './Counter'

describe('Counter Component', () => {
  it('renders with initial count', () => {
    render(<Counter initialCount={0} label="Test Counter" />)
    const countDisplay = screen.getByTestId('count-value')
    expect(countDisplay).toHaveTextContent('Count: 0')
  })

  it('increments count by 1 when increment button is clicked', () => {
    render(<Counter initialCount={0} label="Test Counter" />)
    const button = screen.getByRole('button', { name: /increment/i })
    fireEvent.click(button)

    const countDisplay = screen.getByTestId('count-value')
    // Expected to be 1, but due to Bug 2 it will be -1
    expect(countDisplay).toHaveTextContent('Count: 1')
  })
})

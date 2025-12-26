import { useEffect, useState } from "react"

const PLACEHOLDER_TEXTS = [
  "Thinking hard...",
  "Making it better...",
  "Crafting the perfect title...",
  "Brewing something good...",
  "Putting thoughts together...",
  "Finding the right words...",
  "Almost there...",
  "Working on it...",
  "Give me a second...",
  "Processing magic...",
  "Generating brilliance...",
  "Just a moment...",
  "Cooking up a title...",
  "Summoning creativity...",
  "Analyzing the vibes...",
]

interface AnimatedPlaceholderProps {
  className?: string
}

export function AnimatedPlaceholder({ className = "" }: AnimatedPlaceholderProps) {
  const [text, setText] = useState(PLACEHOLDER_TEXTS[0])

  useEffect(() => {
    // Randomly select a placeholder text
    const randomText = PLACEHOLDER_TEXTS[Math.floor(Math.random() * PLACEHOLDER_TEXTS.length)]
    setText(randomText)
  }, [])

  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <span className="relative inline-flex">
        <span className="animate-pulse bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 bg-clip-text text-transparent">
          {text}
        </span>
        <span className="absolute inset-0 animate-pulse opacity-75 blur-sm bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 bg-clip-text text-transparent">
          {text}
        </span>
      </span>
      <span className="flex gap-1">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="w-1.5 h-1.5 rounded-full bg-pink-500 animate-bounce" style={{ animationDelay: "300ms" }} />
      </span>
    </span>
  )
}

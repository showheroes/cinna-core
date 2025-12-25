import { Wrench, CheckCircle2, Circle, Loader2 } from "lucide-react"

interface TodoItem {
  content: string
  activeForm: string
  status: "completed" | "in_progress" | "pending"
}

interface TodoWriteToolBlockProps {
  todos: TodoItem[]
}

export function TodoWriteToolBlock({ todos }: TodoWriteToolBlockProps) {
  return (
    <div className="flex items-start gap-2 text-sm bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded px-3 py-2">
      <Wrench className="h-4 w-4 text-blue-600 dark:text-blue-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="font-medium text-blue-900 dark:text-blue-100 mb-2">
          Task List Updated
        </div>
        <div className="space-y-1.5">
          {todos.map((todo, index) => {
            const Icon = todo.status === "completed"
              ? CheckCircle2
              : todo.status === "in_progress"
              ? Loader2
              : Circle

            const iconColor = todo.status === "completed"
              ? "text-green-600 dark:text-green-400"
              : todo.status === "in_progress"
              ? "text-blue-600 dark:text-blue-400"
              : "text-gray-400 dark:text-gray-600"

            const textColor = todo.status === "completed"
              ? "text-gray-500 dark:text-gray-500 line-through"
              : "text-blue-900 dark:text-blue-100"

            return (
              <div key={index} className="flex items-start gap-2">
                <Icon
                  className={`h-4 w-4 mt-0.5 flex-shrink-0 ${iconColor} ${
                    todo.status === "in_progress" ? "animate-spin" : ""
                  }`}
                />
                <span className={`${textColor} text-sm`}>
                  {todo.status === "in_progress" ? todo.activeForm : todo.content}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

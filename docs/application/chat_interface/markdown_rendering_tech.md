# Markdown Rendering — Technical Reference

## File Locations

- `frontend/src/components/Chat/MarkdownRenderer.tsx` — Single component, wraps `react-markdown` + `remark-gfm`

## Component Interface

`MarkdownRendererProps`:
- `content: string` — Raw markdown text to render
- `className?: string` — Tailwind classes applied to outer div (typically Tailwind Typography `prose` variants)

## Custom Component Overrides

The component overrides two `react-markdown` components:

### `code`
- Detects block vs inline via `language-*` CSS class regex: `/language-(\w+)/.exec(className)`
- **Inline code**: `bg-slate-900 text-slate-900 dark:text-slate-100 px-1.5 py-0.5 rounded font-mono text-sm`
- **Code blocks**: `block bg-slate-900 text-slate-100 p-3 rounded-md font-mono text-xs overflow-x-auto border border-slate-700`

### `pre`
- Wraps children in `<div className="not-prose my-2">` to escape Tailwind Typography constraints on code blocks

## Libraries

- `react-markdown` — Core markdown-to-React renderer
- `remark-gfm` — GitHub-flavored markdown plugin (tables, strikethrough, task lists, autolinks)

## Extending

To add syntax highlighting: install `rehype-highlight` or `react-syntax-highlighter`, modify the `code` component override to use language detection for coloring. The `match` variable already captures the language from the className.

import { Fragment, memo, type ReactNode } from 'react'

/** Bold, italics and `code` inside one line. Builds React nodes, so model output is never parsed as HTML. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    if (t.startsWith('**')) out.push(<strong key={m.index}>{t.slice(2, -2)}</strong>)
    else if (t.startsWith('`')) out.push(<code key={m.index}>{t.slice(1, -1)}</code>)
    else out.push(<em key={m.index}>{t.slice(1, -1)}</em>)
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

const cells = (row: string) => row.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((c) => c.trim())
const isRule = (l: string) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.includes('-')

/** The small slice of Markdown the assistant actually writes: headings, lists, tables, emphasis. */
function Markdown({ text }: { text: string }) {
  const lines = text.split(/\r?\n/)
  const blocks: ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
    } else if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      i++
    } else if (/^\s*>/.test(line)) {
      const quote: string[] = []
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''))
      blocks.push(<blockquote key={i}><Markdown text={quote.join('\n')} /></blockquote>)
    } else if (/^#{1,6}\s/.test(line)) {
      blocks.push(<h4 key={i}>{inline(line.replace(/^#+\s*/, ''))}</h4>)
      i++
    } else if (line.includes('|') && i + 1 < lines.length && isRule(lines[i + 1])) {
      const head = cells(line)
      const rows: string[][] = []
      let j = i + 2
      while (j < lines.length && lines[j].includes('|')) rows.push(cells(lines[j++]))
      blocks.push(
        <div className="md-table" key={i}>
          <table>
            <thead><tr>{head.map((h, k) => <th key={k}>{inline(h)}</th>)}</tr></thead>
            <tbody>{rows.map((r, a) => <tr key={a}>{r.map((c, k) => <td key={k}>{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      )
      i = j
    } else if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d/.test(line)
      const items: string[] = []
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*•]|\d+[.)])\s+/, ''))
      const body = items.map((t, k) => <li key={k}>{inline(t)}</li>)
      blocks.push(ordered ? <ol key={i}>{body}</ol> : <ul key={i}>{body}</ul>)
    } else {
      const para: string[] = []
      while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|\s*>|\s*([-*•]|\d+[.)])\s+)/.test(lines[i]) && !(i + 1 < lines.length && lines[i].includes('|') && isRule(lines[i + 1]))) para.push(lines[i++])
      blocks.push(
        <p key={i}>
          {para.map((l, k) => (
            <Fragment key={k}>
              {k > 0 && <br />}
              {inline(l)}
            </Fragment>
          ))}
        </p>,
      )
    }
  }
  return <div className="cp-md">{blocks}</div>
}

export default memo(Markdown)

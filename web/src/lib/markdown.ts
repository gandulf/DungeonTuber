/**
 * Minimal Markdown to HTML for the answers of the AI assistant: headings, lists, bold, italic, code and paragraphs.
 * Everything is escaped first, so the answer can never inject HTML.
 */

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function inline(text: string): string {
  return escape(text)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/__([^_]+)__/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\w)/g, '$1<em>$2</em>')
    .replace(/(^|[^_\w])_([^_\s][^_]*?)_(?!\w)/g, '$1<em>$2</em>');
}

export function markdown(source: string): string {
  const html: string[] = [];
  let list: 'ul' | 'ol' | null = null;
  let paragraph: string[] = [];

  const closeParagraph = () => {
    if (paragraph.length) html.push(`<p>${paragraph.map(inline).join('<br>')}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (list) html.push(`</${list}>`);
    list = null;
  };

  for (const raw of source.replace(/\r\n?/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (!line.trim()) {
      closeParagraph();
      closeList();
    } else if (heading) {
      closeParagraph();
      closeList();
      const level = Math.min(6, heading[1].length + 2); // the chat is small: # becomes h3
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
    } else if (bullet || numbered) {
      closeParagraph();
      const kind = bullet ? 'ul' : 'ol';
      if (list !== kind) {
        closeList();
        html.push(`<${kind}>`);
        list = kind;
      }
      html.push(`<li>${inline((bullet ?? numbered)![1])}</li>`);
    } else if (/^(-{3,}|\*{3,})$/.test(line.trim())) {
      closeParagraph();
      closeList();
      html.push('<hr>');
    } else {
      closeList();
      paragraph.push(line.trim());
    }
  }
  closeParagraph();
  closeList();
  return html.join('');
}

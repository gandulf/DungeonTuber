import { describe, expect, it } from 'vitest';
import { markdown } from './markdown';

describe('markdown', () => {
  it('renders paragraphs, emphasis and code', () => {
    expect(markdown('**Initiative** ist *wichtig*\nund `1W6`.\n\nZweiter Absatz')).toBe(
      '<p><strong>Initiative</strong> ist <em>wichtig</em><br>und <code>1W6</code>.</p><p>Zweiter Absatz</p>');
  });

  it('renders headings and lists', () => {
    expect(markdown('## Ablauf\n1. Würfeln\n2. Vergleichen\n- a\n- b')).toBe(
      '<h4>Ablauf</h4><ol><li>Würfeln</li><li>Vergleichen</li></ol><ul><li>a</li><li>b</li></ul>');
  });

  it('never lets HTML through', () => {
    expect(markdown('<img src=x onerror=alert(1)> **<b>x</b>**')).toBe(
      '<p>&lt;img src=x onerror=alert(1)&gt; <strong>&lt;b&gt;x&lt;/b&gt;</strong></p>');
  });

  it('keeps multiplications and snake_case words', () => {
    expect(markdown('2 * 3 * 4 and my_var_name')).toBe('<p>2 * 3 * 4 and my_var_name</p>');
  });
});

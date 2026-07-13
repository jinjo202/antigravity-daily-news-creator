# Daily News Reporter Creator - Project Specific Rules

This repository contains strict constraints for formatting Daily Market Report emails sent via SMTP to ensure Microsoft Outlook and Knox Mail render them in a clean, rectangular, justified style without stretching the last line of a paragraph or causing double newlines.

## HTML Email Formatting and Justification Constraints

### 1. Document Width and Line Wrapping
* **Use HTML `<br>` Tags for Line Breaks**: Inside a paragraph block, use `<br>` tags to join the wrapped lines to ensure Outlook renders the layout smoothly.
* **Wrap at 40 Characters**: When generating or parsing long text, wrap the lines at **max_len=40** characters (using word boundaries/spaces).

### 2. Justification and Alignment Rules (Line-by-Line / Paragraph-by-Paragraph)
* **Justified Text (Long Body)**: Apply `align="justify"` and `style="text-align: justify; text-justify: inter-character; word-break: break-all;"` ONLY to normal paragraphs where the total length of the combined lines is **>= 28 characters** and does not contain greetings or sign-offs.
* **Left-Aligned Text (Short/Structural)**: Apply `align="left"` (or omit justify align) and `style="text-align: left;"` to:
  * Greetings ("안녕하십니까", "금일 아시아 증시 시황 보고 드립니다.")
  * Sign-offs ("감사합니다.", "드림", "올림")
  * Paragraphs/lines shorter than **28 characters**
  * List items (`list_item`, starting with `*`)
  * Footnotes (`footnote`, starting with `※`)
  * Empty spacing paragraphs (`empty`)

### 3. Font and Layout Styling Parameters
To perfectly match the verified Samsung/TrendForce layout, strictly apply these inline CSS styles:
* **Common Paragraph CSS**: `font-family: 굴림, sans-serif; font-size: 12pt; line-height: 1.5; margin: 5px 0px 10.66px; padding: 0px; background-color: rgb(255,255,255);` (Ensure `margin` is strictly `5px 0px 10.66px` and `line-height` is `1.5`).
* **Footnote / List Item Blue Color**: Footnotes and list items must have blue text (`color: blue;`) on 바탕체/serif font.
* **Global Overrides**: Never put `text-align: justify !important;` in the global `<style>` block in the HTML `<head>`, as it overrides the specific left-aligned inline styling for greetings and footnotes.

---

## Code Reference Summary (`send_email.py`)
Ensure `convert_text_to_html` always uses `wrap_line_by_words(text, max_len=40)` and joins them with `<br>`, maintaining the alignment conditions.

"""Centralized Claude prompt templates for remediation generation.

Keep all model-facing copy here so prompts are easy to review and tune.
"""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are an expert accessibility engineer writing remediation guidance for \
developers and product managers.

Given a group of related accessibility violations from an automated audit \
(Lucid / axe-core style), produce practical, accurate guidance.

Rules:
- Write for a mixed audience: engineers need concrete code fixes; PMs need \
user impact in plain language.
- Prefer specific HTML/ARIA/CSS/JS fixes over vague advice.
- Reference WCAG criteria by number when relevant.
- Do not invent violations that were not provided.
- Keep each field concise but complete (2–5 sentences for explanation and \
why_it_matters; fix_suggestion may include a short code example in markdown).
- Respond with valid JSON only — no markdown fences, no commentary outside JSON.
"""

USER_PROMPT_TEMPLATE = """\
Generate remediation guidance for this accessibility violation group.

Rule ID: {rule_id}
Impact: {impact}
WCAG criteria: {wcag_criteria}
Description: {description}
Help URL: {help_url}
Occurrence count: {count}

Affected selectors:
{selectors}

Sample HTML snippets:
{html_snippets}

Return a JSON object with exactly these string fields:
{{
  "explanation": "Plain-English explanation of the issue",
  "why_it_matters": "Why this matters for real users",
  "fix_suggestion": "Concrete code-level fix suggestion"
}}
"""


def build_user_prompt(
    *,
    rule_id: str,
    impact: str,
    wcag_criteria: list[str],
    description: str,
    help_url: str,
    count: int,
    selectors: list[str],
    html_snippets: list[str],
    max_selectors: int = 20,
    max_snippets: int = 5,
) -> str:
    """Render the user prompt for a violation group."""
    shown_selectors = selectors[:max_selectors]
    selector_lines = "\n".join(f"- `{s}`" for s in shown_selectors)
    if len(selectors) > max_selectors:
        selector_lines += f"\n- …and {len(selectors) - max_selectors} more"

    shown_snippets = html_snippets[:max_snippets]
    if shown_snippets:
        snippet_block = "\n\n".join(
            f"```html\n{snippet}\n```" for snippet in shown_snippets
        )
        if len(html_snippets) > max_snippets:
            extra = len(html_snippets) - max_snippets
            snippet_block += f"\n\n…and {extra} more snippets"
    else:
        snippet_block = "(none provided)"

    criteria = ", ".join(wcag_criteria) if wcag_criteria else "(none listed)"

    return USER_PROMPT_TEMPLATE.format(
        rule_id=rule_id,
        impact=impact,
        wcag_criteria=criteria,
        description=description,
        help_url=help_url or "(none)",
        count=count,
        selectors=selector_lines or "(none)",
        html_snippets=snippet_block,
    )

# lucid-insights

Turn [Lucid](https://github.com/thehashton) accessibility audit JSON into a remediation report a developer or PM can actually act on.

Lucid (and tools like axe-core) are excellent at *finding* issues — rule IDs, selectors, WCAG criteria, severity. What they don't do is explain the problem in plain English, why it matters for real users, or how to fix it in code. Pasting raw JSON into a PR review is noise. **lucid-insights** is the companion CLI: it reads Lucid's structured output, batches similar violations, asks Claude for remediation guidance, and renders a prioritized markdown report ready for GitHub or Slack.

## The problem this solves

| Without lucid-insights | With lucid-insights |
| --- | --- |
| Raw rule IDs (`image-alt`, `button-name`) | Plain-English explanations |
| One row per DOM node (50 identical issues) | One section per rule, all selectors listed |
| No prioritization narrative | Grouped by impact: critical → minor |
| Hard to paste into a PR | `--format github-comment` with collapsible details |
| No cost awareness | Token/cost estimate + `--yes` gate for large audits |

## How it plugs into Lucid

```text
lucid audit https://example.com -o audit.json
lucid-insights report --input audit.json --output report.md
```

Lucid produces the audit JSON. lucid-insights consumes that file and never re-crawls the page. Keep both tools in your CI or local a11y workflow:

```bash
# Example CI-style pipeline
lucid audit "$PREVIEW_URL" -o audit.json
lucid-insights report \
  --input audit.json \
  --output report.md \
  --format github-comment \
  --yes
# → paste report.md into the PR review comment
```

### Input schema (Lucid JSON)

lucid-insights expects JSON shaped like this (field names are authoritative for this tool):

```json
{
  "url": "https://example.com/checkout",
  "timestamp": "2026-07-03T14:30:00Z",
  "violations": [
    {
      "id": "image-alt",
      "impact": "critical",
      "wcag_criteria": ["1.1.1"],
      "selector": "img.hero-banner",
      "html_snippet": "<img class=\"hero-banner\" src=\"/hero.jpg\">",
      "description": "Images must have alternate text",
      "help_url": "https://dequeuniversity.com/rules/axe/4.9/image-alt"
    }
  ]
}
```

| Field | Type | Notes |
| --- | --- | --- |
| `url` | string | Page that was audited |
| `timestamp` | ISO-8601 | Accepts trailing `Z` |
| `violations[].id` | string | Rule id (used for batching) |
| `violations[].impact` | enum | `critical` \| `serious` \| `moderate` \| `minor` |
| `violations[].wcag_criteria` | string[] | e.g. `["1.1.1"]` |
| `violations[].selector` | string | CSS selector for the node |
| `violations[].html_snippet` | string | Optional HTML sample |
| `violations[].description` | string | Short rule description |
| `violations[].help_url` | string | Optional reference link |

Violations are **grouped by `id`** before any Claude call. Fifty `image-alt` hits become one explanation plus a list of every affected selector.

## Before / after

**Before** — a single Lucid violation (raw JSON):

```json
{
  "id": "image-alt",
  "impact": "critical",
  "wcag_criteria": ["1.1.1"],
  "selector": "img.hero-banner",
  "html_snippet": "<img class=\"hero-banner\" src=\"/hero.jpg\">",
  "description": "Images must have alternate text",
  "help_url": "https://dequeuniversity.com/rules/axe/4.9/image-alt"
}
```

**After** — generated report snippet:

```markdown
### `image-alt` (3 occurrences)

**Impact:** critical
**WCAG:** 1.1.1

**Affected selectors:**
- `img.hero-banner`
- `img.product-thumb`
- `img.logo`

#### What's wrong

Images on the checkout page are missing alternative text, so assistive
technologies have nothing meaningful to announce for those visuals.

#### Why it matters

Screen reader users cannot tell whether an image is decorative, a product
photo, or critical UI chrome — they may miss context needed to complete
checkout.

#### How to fix it

Add a concise `alt` attribute that describes the image purpose, for example:

```html
<img class="hero-banner" src="/hero.jpg" alt="Secure checkout — free returns">
```

Use `alt=""` only for purely decorative images.
```

## Install

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/thehashton/lucid-insights.git
cd lucid-insights
uv sync
```

Or install the CLI into your environment:

```bash
uv tool install .
# or: pip install .
```

Set your Anthropic API key (never commit it):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Full markdown report

```bash
uv run lucid-insights report \
  --input audit.json \
  --output report.md
```

### GitHub PR comment

Shorter layout; moderate/minor issues collapse into `<details>` blocks:

```bash
uv run lucid-insights report \
  --input audit.json \
  --format github-comment \
  --output pr-comment.md
```

### Slack summary

Top 5 issues plus a pointer to the full report:

```bash
uv run lucid-insights report \
  --input audit.json \
  --format slack \
  --full-report report.md
```

### Options

| Flag | Default | Description |
| --- | --- | --- |
| `--input` / `-i` | *required* | Path to Lucid audit JSON |
| `--output` / `-o` | stdout | Write report to a file |
| `--format` / `-f` | `markdown` | `markdown`, `github-comment`, or `slack` |
| `--model` / `-m` | `claude-sonnet-5` | Claude model ID ([docs](https://docs.claude.com/en/docs/about-claude/models/overview)) |
| `--yes` / `-y` | off | Proceed when group count exceeds the cost threshold |
| `--cost-threshold` | `10` | Require `--yes` above this many uncached groups |
| `--diff-against` | — | Only report new/changed rules vs a previous `report.md` |
| `--cache` / `--no-cache` | cache on | Cache Claude responses per violation-group hash |
| `--cache-dir` | `~/.cache/lucid-insights` | Override cache location |
| `--full-report` | — | Path printed in Slack summaries |

### Cost gate

Before calling Claude, lucid-insights prints an approximate token and USD estimate. If the number of **uncached** violation groups exceeds `--cost-threshold` (default **10**), the command exits with code `2` unless you pass `--yes`:

```text
Cost estimate for 14 API call(s) (claude-sonnet-5):
  ~9,800 input tokens, ~4,900 output tokens
  ~$0.1029 USD (approximate)
Group count (14) exceeds threshold (10). Re-run with --yes to proceed.
```

### Diff mode (CI regression tracking)

Reports embed a machine-readable fingerprint. Pass the previous report to only generate guidance for **new or changed** rule groups:

```bash
uv run lucid-insights report \
  --input audit.json \
  --diff-against previous-report.md \
  --output report.md \
  --yes
```

### Response cache

By default, insights are cached under `~/.cache/lucid-insights`, keyed by a hash of the rule id, impact, description, selectors, and snippets. Repeat runs on unchanged issues skip the API.

## Project layout

```text
src/lucid_insights/
  cli.py              # Typer commands
  models.py           # Pydantic input + report models
  grouping.py         # Batch violations by rule id
  prompts.py          # All Claude prompt templates (tune here)
  claude_client.py    # Anthropic SDK wrapper + cost estimates
  cache.py            # Disk cache for insights
  diff.py             # --diff-against support
  renderer.py         # Jinja2 rendering
  templates/          # markdown, github-comment, slack
tests/
  fixtures/sample_audit.json
  test_*.py
```

## Development

```bash
uv sync
uv run ruff check .
uv run pytest
```

All Anthropic calls are mocked in tests — CI never needs a real API key.

## Roadmap

- [x] `--diff-against previous-report.md` for regression-only reporting
- [x] Disk cache of Claude responses per violation-group hash
- [ ] Optional HTML report format
- [ ] Direct GitHub PR comment posting via `gh` / API
- [ ] Streaming progress for very large audits

## License

MIT — see [LICENSE](LICENSE).

# CI Configuration for ZLB Golden Test

## Nightly Schedule

The ZLB golden test runs every night at 2 AM to validate pipeline integrity.

```yaml
# .github/workflows/nightly-golden-test.yml
name: Nightly Golden Test

on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily
  workflow_dispatch:  # Allow manual trigger

jobs:
  zlb-golden:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e .
          pip install -e .[dev]
      
      - name: Run ZLB golden test
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python -m pytest tests/integration_real/test_zlb_golden.py -v -s
      
      - name: Upload artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: zlb-failure-artifacts
          path: |
            /tmp/zlb_test/**/*.json
            /tmp/zlb_test/**/*.log
          retention-days: 7
      
      - name: Notify on failure
        if: failure()
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "🚨 ZLB Golden Test Failed",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*ZLB Golden Test Failed*\n\nThe pipeline is broken. See workflow run for details."
                  }
                },
                {
                  "type": "actions",
                  "elements": [
                    {
                      "type": "button",
                      "text": {
                        "type": "plain_text",
                        "text": "View Logs"
                      },
                      "url": "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"
                    }
                  ]
                }
              ]
            }
```

## Manual Testing

Run the golden test locally (requires API key):

```bash
# Full test (~20 min, ~$10)
python -m pytest tests/integration_real/test_zlb_golden.py -v -s

# Or run directly
python tests/integration_real/test_zlb_golden.py
```

## Test Selection

Run only fast tests in PR CI:

```bash
# Exclude expensive tests
pytest -m "not expensive"

# Exclude real document tests
pytest -m "not real"

# Run only unit tests
pytest tests/ -m "not (real or expensive or requires_model)"
```

## Cost Control

The golden test costs approximately $10 per run due to:
- ~1,100 concept extractions
- ~50 unit rewrites
- Each unit is 50-200 lines of LaTeX

To minimize cost during development:
1. Use mock mode for CLI integration tests
2. Test on small fixtures first (equation/001.tex)
3. Run golden test only before release or when pipeline changes
4. Set up billing alerts in Anthropic console

## Alert Threshold

If the golden test fails:
1. **STOP all releases** - the pipeline is broken
2. Check the failure phase (inventory/plan/rewrite/assembly)
3. Review the fixture answer key - did expectations change?
4. If answer key needs updating, document why in commit message
5. Do NOT merge changes that break the golden test

## Expected Stability

This test should have >99% pass rate. Failures indicate:
- Model behavior change (concept correspondence drops)
- Planner regression (units become non-contiguous or overlap)
- Assembly regression (patches fail to apply)
- Infrastructure issue (timeout, API error)

Investigate every failure. Do not accept "flaky" as an explanation.

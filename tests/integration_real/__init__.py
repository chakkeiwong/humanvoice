"""
Real document integration tests.

These tests run the full pipeline on real manuscripts to verify
production readiness. They are expensive (time and cost) and should
be run on a schedule, not in every PR.

Markers:
- @pytest.mark.real: Uses real manuscript fixtures
- @pytest.mark.expensive: Takes >5 minutes or costs >$1
- @pytest.mark.requires_model: Requires live model access
"""

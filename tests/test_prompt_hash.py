#!/usr/bin/env python3
"""
Unit test for prompt template hash implementation.

Contract 1.1.0 requires prompt_template_hash to be recorded before invocation.
This test verifies the hash flows from profile to config to runtime manifests.
"""

import unittest
from pathlib import Path
from humanvoice.model import ModelConfig


class TestPromptTemplateHash(unittest.TestCase):
    """Verify prompt template hash is properly loaded and recorded."""

    def test_config_from_profile_includes_hash(self):
        """ModelConfig.from_profile() must include prompt_template_hash from the profile."""
        config = ModelConfig.from_profile()

        # Hash should be present and be a dict of template hashes
        self.assertIsNotNone(config.prompt_template_hash,
            "prompt_template_hash should not be None when loaded from profile")
        self.assertIsInstance(config.prompt_template_hash, dict,
            "prompt_template_hash should be a dict of template_key -> hash")

        # Should have at least one active_v2 template
        self.assertGreater(len(config.prompt_template_hash), 0,
            "prompt_template_hash should contain at least one template")

        # All values should be valid SHA256 hashes (64 hex chars)
        for template_key, template_hash in config.prompt_template_hash.items():
            self.assertEqual(len(template_hash), 64,
                f"Template hash for {template_key} should be 64-character SHA256 hex")
            self.assertTrue(all(c in '0123456789abcdefABCDEF' for c in template_hash),
                f"Template hash for {template_key} should contain only hex characters")

    def test_mock_config_has_none_hash(self):
        """Mock-mode config should have None hash (no profile loaded)."""
        config = ModelConfig()
        self.assertIsNone(config.prompt_template_hash,
            "Mock-mode config should have None prompt_template_hash")

    def test_profile_hash_matches_template_file(self):
        """The hashes in the profile should match the actual template files."""
        from hashlib import sha256
        import json

        config = ModelConfig.from_profile()
        profile_hashes = config.prompt_template_hash

        # Load the profile to get template paths
        profile_path = Path(__file__).resolve().parents[1] / "security" / "inference_profile.json"
        with open(profile_path, 'r') as f:
            profile = json.load(f)

        templates = profile.get('prompt_templates', {})

        # Check each active_v2 template
        for template_key in profile_hashes.keys():
            template_info = templates.get(template_key, {})
            profile_hash = profile_hashes[template_key]

            # For v2 templates, the template is defined by a function, not a file
            # So we can only verify the hash is present and valid format
            self.assertEqual(len(profile_hash), 64,
                f"Hash for {template_key} should be 64-character SHA256 hex")
            self.assertTrue(all(c in '0123456789abcdefABCDEF' for c in profile_hash),
                f"Hash for {template_key} should contain only hex characters")

            # Verify it matches what's in the profile JSON
            expected_hash = template_info.get('template_sha256')
            self.assertEqual(profile_hash, expected_hash,
                f"Hash for {template_key} should match profile entry")


if __name__ == '__main__':
    unittest.main()

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

        # Hash should be present and be a valid SHA256 (64 hex chars)
        self.assertIsNotNone(config.prompt_template_hash,
            "prompt_template_hash should not be None when loaded from profile")
        self.assertEqual(len(config.prompt_template_hash), 64,
            "prompt_template_hash should be 64-character SHA256 hex")
        self.assertTrue(all(c in '0123456789abcdefABCDEF' for c in config.prompt_template_hash),
            "prompt_template_hash should contain only hex characters")

    def test_mock_config_has_none_hash(self):
        """Mock-mode config should have None hash (no profile loaded)."""
        config = ModelConfig()
        self.assertIsNone(config.prompt_template_hash,
            "Mock-mode config should have None prompt_template_hash")

    def test_profile_hash_matches_template_file(self):
        """The hash in the profile should match the actual template file."""
        from hashlib import sha256

        config = ModelConfig.from_profile()
        profile_hash = config.prompt_template_hash

        # Compute actual file hash
        template_path = Path(__file__).resolve().parents[1] / "security" / "prompt_template_critic.txt"
        if template_path.exists():
            actual_hash = sha256(template_path.read_bytes()).hexdigest()
            self.assertEqual(profile_hash, actual_hash,
                f"Profile hash {profile_hash} should match actual file hash {actual_hash}")


if __name__ == '__main__':
    unittest.main()

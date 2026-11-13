"""Resolve phase endpoints from the same selected config as the native writer.

The retained writer already uses ModelConfig.runtime_type. Its default phase
validator instead consults an environment selector a second time. Apply this
only around prospective native consumers; never rewrite a saved binding or
change the implementation that produced a paid receipt.
"""

import sys
from contextlib import contextmanager

from humanvoice import artifacts
from humanvoice.model import ModelConfig
from tools.delayed_network_runtime import replaced_aliases


@contextmanager
def scope():
    native = artifacts.phase_bindings

    def phase_bindings(snapshot, baseline, plan, api_endpoint=None):
        config = ModelConfig.from_profile()
        if config.runtime_type == 'codex-cli':
            # The exact versioned URL is part of the admitted profile. Do not
            # strip /v1 or treat different paths as equivalent destinations.
            if api_endpoint is not None and api_endpoint != config.api_endpoint:
                raise ValueError('Writer endpoint differs from the selected runtime')
            api_endpoint = config.api_endpoint
        return native(snapshot, baseline, plan, api_endpoint=api_endpoint)

    with replaced_aliases(native, phase_bindings):
        try:
            yield
        finally:
            # A consumer imported during the scope may capture the temporary
            # function. Restore those aliases as well as the original imports.
            for name, module in list(sys.modules.items()):
                if module is not None and name.startswith(('humanvoice.', 'tools.')):
                    for key, value in list(vars(module).items()):
                        if value is phase_bindings:
                            setattr(module, key, native)

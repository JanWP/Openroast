import tempfile
from unittest import mock


class ConfigSandboxMixin:
    """Isolate app_config file I/O to a per-test temporary config path."""

    def setUp(self):
        super().setUp()
        self._config_tmpdir = tempfile.TemporaryDirectory()
        self._config_path = f"{self._config_tmpdir.name}/config.json"
        self._config_path_patcher = mock.patch(
            "openroast.app_config.get_config_path",
            return_value=self._config_path,
        )
        self._config_path_patcher.start()

    def tearDown(self):
        self._config_path_patcher.stop()
        self._config_tmpdir.cleanup()
        super().tearDown()


"""
Tests for the configuration management module.
"""

import os
import pytest
import tempfile
from unittest.mock import patch

import sys
sys.path.insert(0, 'src')

from asus_router_exporter.core.config import Config
from asus_router_exporter.core.exceptions import ConfigurationError


class TestConfigDefaults:
    """Tests for default configuration."""

    def test_default_config_has_router_section(self):
        config = Config.from_env()
        assert config.get('router') is not None
        assert 'host' in config.get('router')
        assert 'auth' in config.get('router')

    def test_default_config_has_exporter_section(self):
        config = Config.from_env()
        assert config.get('exporter') is not None
        assert config.get('exporter.port') == 8000
        assert config.get('exporter.scrape_interval') == 30

    def test_default_config_has_collectors_section(self):
        config = Config.from_env()
        collectors = config.get('collectors')
        assert collectors is not None
        assert 'cpu' in collectors
        assert 'memory' in collectors
        assert 'temperature' in collectors

    def test_default_collector_is_enabled(self):
        config = Config.from_env()
        assert config.is_collector_enabled('cpu') is True
        assert config.is_collector_enabled('memory') is True

    def test_default_error_handling_config(self):
        config = Config.from_env()
        assert config.get('error_handling.retry.enabled') is True
        assert config.get('error_handling.retry.max_attempts') == 3
        assert config.get('error_handling.circuit_breaker.enabled') is True


class TestConfigDotNotation:
    """Tests for dot notation access."""

    def test_get_nested_value(self):
        config = Config({'level1': {'level2': {'level3': 'value'}}})
        assert config.get('level1.level2.level3') == 'value'

    def test_get_with_default(self):
        config = Config({})
        assert config.get('nonexistent.key', 'default') == 'default'

    def test_get_nonexistent_returns_none(self):
        config = Config({})
        assert config.get('nonexistent') is None

    def test_get_intermediate_nonexistent(self):
        config = Config({'level1': 'value'})
        assert config.get('level1.level2.level3', 'default') == 'default'


class TestConfigEnvVarSubstitution:
    """Tests for environment variable substitution."""

    def test_substitute_env_var(self):
        with patch.dict(os.environ, {'TEST_VAR': 'test_value'}):
            config = Config({'key': '${TEST_VAR}'})
            assert config.get('key') == 'test_value'

    def test_substitute_env_var_with_default(self):
        # Make sure the var doesn't exist
        os.environ.pop('NONEXISTENT_VAR', None)
        config = Config({'key': '${NONEXISTENT_VAR:default_value}'})
        assert config.get('key') == 'default_value'

    def test_substitute_env_var_empty_default(self):
        os.environ.pop('NONEXISTENT_VAR', None)
        config = Config({'key': '${NONEXISTENT_VAR:}'})
        assert config.get('key') == ''

    def test_substitute_env_var_no_default(self):
        os.environ.pop('NONEXISTENT_VAR', None)
        config = Config({'key': '${NONEXISTENT_VAR}'})
        assert config.get('key') == ''

    def test_substitute_nested_env_vars(self):
        with patch.dict(os.environ, {'VAR1': 'value1', 'VAR2': 'value2'}):
            config = Config({
                'level1': {
                    'key1': '${VAR1}',
                    'key2': '${VAR2}'
                }
            })
            assert config.get('level1.key1') == 'value1'
            assert config.get('level1.key2') == 'value2'


class TestConfigYamlLoading:
    """Tests for YAML configuration loading."""

    @pytest.fixture(autouse=True)
    def require_yaml(self):
        pytest.importorskip("yaml", reason="PyYAML not installed")

    def test_load_yaml_config(self):
        yaml_content = """
router:
  host: 10.0.0.1
  timeout: 30
collectors:
  cpu:
    enabled: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = Config.load(f.name)
                assert config.get('router.host') == '10.0.0.1'
                assert config.get('router.timeout') == 30
                assert config.is_collector_enabled('cpu') is False
            finally:
                os.unlink(f.name)

    def test_load_nonexistent_file_uses_defaults(self):
        config = Config.load('/nonexistent/path.yaml')
        # Should use defaults
        assert config.get('exporter.port') == 8000

    def test_yaml_merges_with_defaults(self):
        yaml_content = """
router:
  host: 10.0.0.1
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = Config.load(f.name)
                # Custom value from YAML
                assert config.get('router.host') == '10.0.0.1'
                # Default value (not in YAML)
                assert config.get('exporter.port') == 8000
            finally:
                os.unlink(f.name)


class TestConfigCollectorConfig:
    """Tests for collector configuration access."""

    def test_get_collector_config(self):
        config = Config({
            'collectors': {
                'cpu': {'enabled': True, 'custom_option': 'value'}
            }
        })
        cpu_config = config.get_collector_config('cpu')
        assert cpu_config['enabled'] is True
        assert cpu_config['custom_option'] == 'value'

    def test_get_nonexistent_collector_config(self):
        config = Config({'collectors': {}})
        result = config.get_collector_config('nonexistent')
        assert result == {}


class TestConfigDeepMerge:
    """Tests for deep merge functionality."""

    def test_deep_merge_nested(self):
        result = Config._deep_merge(
            {'a': {'b': 1, 'c': 2}},
            {'a': {'b': 10}}
        )
        assert result == {'a': {'b': 10, 'c': 2}}

    def test_deep_merge_override_non_dict(self):
        result = Config._deep_merge(
            {'a': {'b': 1}},
            {'a': 'string'}
        )
        assert result == {'a': 'string'}

    def test_deep_merge_add_new_keys(self):
        result = Config._deep_merge(
            {'a': 1},
            {'b': 2}
        )
        assert result == {'a': 1, 'b': 2}


class TestConfigToDict:
    """Tests for to_dict method."""

    def test_to_dict_returns_copy(self):
        original_data = {'key': 'value'}
        config = Config(original_data)
        result = config.to_dict()

        # Modify the result
        result['key'] = 'modified'

        # Original should be unchanged
        assert config.get('key') == 'value'

    def test_repr(self):
        config = Config({'router': {}, 'exporter': {}})
        repr_str = repr(config)
        assert 'router' in repr_str
        assert 'exporter' in repr_str

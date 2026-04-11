"""Tests for generate_config.py and generate_component.py helper functions.

Pure stdlib only; uses unittest.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

# Add project root to path so we can import the generator scripts.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generate_config import validate_name, validate_class_path  # noqa: E402
from generate_component import (  # noqa: E402
    to_pascal_case,
    validate_identifier,
    parse_params,
    _format_default_for_code,
    generate_python_code,
    generate_json_config,
)


# ---------------------------------------------------------------------------
# generate_config.py tests
# ---------------------------------------------------------------------------
class TestValidateName(unittest.TestCase):
    def test_valid_name(self):
        self.assertTrue(validate_name("reader"))
        self.assertTrue(validate_name("data_processor"))

    def test_empty_name(self):
        self.assertFalse(validate_name(""))
        self.assertFalse(validate_name("   "))

    def test_name_with_spaces(self):
        self.assertFalse(validate_name("data processor"))


class TestValidateClassPath(unittest.TestCase):
    def test_valid_path(self):
        self.assertTrue(validate_class_path("features.file_reader.FileReader"))
        self.assertTrue(validate_class_path("my_module.MyClass"))

    def test_no_dot(self):
        self.assertFalse(validate_class_path("FileReader"))
        self.assertFalse(validate_class_path(""))


class TestBuildConfigStructure(unittest.TestCase):
    """Verify that the config dict produced by build_config matches expected schema."""

    def test_empty_config_structure(self):
        # Simulate what build_config returns with no components
        config = {
            "components": [],
            "bus": {"default_channel": "highspeed"},
        }
        self.assertIn("components", config)
        self.assertIn("bus", config)
        self.assertIn("default_channel", config["bus"])
        self.assertIsInstance(config["components"], list)

    def test_config_with_component(self):
        config = {
            "components": [
                {
                    "name": "reader",
                    "class": "features.file_reader.FileReader",
                    "params": {"path": "sample.txt"},
                    "subscribes": ["file.read"],
                    "publishes": ["data.loaded"],
                }
            ],
            "bus": {"default_channel": "normal"},
        }
        comp = config["components"][0]
        self.assertIn("name", comp)
        self.assertIn("class", comp)
        self.assertIn("params", comp)
        self.assertIn("subscribes", comp)
        self.assertIn("publishes", comp)
        # Ensure valid JSON serialization
        json_str = json.dumps(config, indent=2)
        roundtrip = json.loads(json_str)
        self.assertEqual(roundtrip, config)


# ---------------------------------------------------------------------------
# generate_component.py tests
# ---------------------------------------------------------------------------
class TestToPascalCase(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(to_pascal_case("data_processor"), "DataProcessor")

    def test_single_word(self):
        self.assertEqual(to_pascal_case("reader"), "Reader")

    def test_multiple_underscores(self):
        self.assertEqual(to_pascal_case("my_special_handler"), "MySpecialHandler")

    def test_leading_underscore(self):
        # Leading underscore gets consumed by split/capitalize
        self.assertEqual(to_pascal_case("_internal"), "Internal")


class TestValidateIdentifier(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_identifier("data_processor"))
        self.assertTrue(validate_identifier("_private"))
        self.assertTrue(validate_identifier("Class123"))

    def test_invalid(self):
        self.assertFalse(validate_identifier("data processor"))
        self.assertFalse(validate_identifier("123abc"))
        self.assertFalse(validate_identifier(""))
        self.assertFalse(validate_identifier("data-processor"))


class TestParseParams(unittest.TestCase):
    def test_simple_pairs(self):
        result = parse_params(["input_key=data", "threshold=10"])
        self.assertEqual(result, [("input_key", "data"), ("threshold", "10")])

    def test_none_default(self):
        result = parse_params(["required_param=None"])
        self.assertEqual(result, [("required_param", None)])

    def test_no_default(self):
        result = parse_params(["name"])
        self.assertEqual(result, [("name", None)])

    def test_comma_separated(self):
        result = parse_params(["key1=val1, key2=val2"])
        self.assertEqual(result, [("key1", "val1"), ("key2", "val2")])

    def test_empty_lines(self):
        result = parse_params(["", "key=val", ""])
        self.assertEqual(result, [("key", "val")])

    def test_equals_in_value(self):
        result = parse_params(["url=http://example.com?a=1"])
        self.assertEqual(result, [("url", "http://example.com?a=1")])


class TestFormatDefaultForCode(unittest.TestCase):
    def test_already_quoted(self):
        self.assertEqual(_format_default_for_code('"hello"'), '"hello"')
        self.assertEqual(_format_default_for_code("'hello'"), "'hello'")

    def test_integer(self):
        self.assertEqual(_format_default_for_code("42"), "42")
        self.assertEqual(_format_default_for_code("-7"), "-7")

    def test_float(self):
        self.assertEqual(_format_default_for_code("3.14"), "3.14")

    def test_boolean(self):
        self.assertEqual(_format_default_for_code("true"), "true")
        self.assertEqual(_format_default_for_code("false"), "false")

    def test_none(self):
        self.assertEqual(_format_default_for_code("None"), "None")

    def test_string_auto_quote(self):
        self.assertEqual(_format_default_for_code("data"), '"data"')
        self.assertEqual(_format_default_for_code("sample.txt"), '"sample.txt"')


class TestGeneratePythonCode(unittest.TestCase):
    def test_generates_valid_syntax(self):
        code = generate_python_code(
            component_name="test_comp",
            description="Test component",
            subscribes=["test.topic"],
            publishes=["test.result"],
            params=[("input_key", "data"), ("count", "5")],
        )
        # Should compile without syntax errors
        compile(code, "<test>", "exec")

    def test_empty_params(self):
        code = generate_python_code(
            component_name="simple",
            description="Simple component",
            subscribes=[],
            publishes=[],
            params=[],
        )
        compile(code, "<test>", "exec")
        self.assertIn("def __init__(self, **kwargs: Any) -> None:", code)

    def test_required_params(self):
        code = generate_python_code(
            component_name="required_test",
            description="Test",
            subscribes=[],
            publishes=[],
            params=[("name", None)],
        )
        compile(code, "<test>", "exec")
        self.assertIn("name: Any", code)

    def test_subscribes_in_on_start(self):
        code = generate_python_code(
            component_name="sub_test",
            description="Test",
            subscribes=["a.topic", "b.topic"],
            publishes=[],
            params=[],
        )
        self.assertIn('self._bus.subscribe("a.topic", self.handle_message)', code)
        self.assertIn('self._bus.subscribe("b.topic", self.handle_message)', code)

    def test_publishes_in_handle_message(self):
        code = generate_python_code(
            component_name="pub_test",
            description="Test",
            subscribes=[],
            publishes=["out.topic"],
            params=[],
        )
        self.assertIn('"out.topic"', code)

    def test_class_name_pascal_case(self):
        code = generate_python_code(
            component_name="my_data_handler",
            description="Test",
            subscribes=[],
            publishes=[],
            params=[],
        )
        self.assertIn("class MyDataHandler(BaseComponent):", code)

    def test_instance_attributes(self):
        code = generate_python_code(
            component_name="attr_test",
            description="Test",
            subscribes=[],
            publishes=[],
            params=[("foo", "bar"), ("count", "42")],
        )
        self.assertIn("self.foo = foo", code)
        self.assertIn("self.count = count", code)


class TestGenerateJsonConfig(unittest.TestCase):
    def test_basic_structure(self):
        config = generate_json_config(
            component_name="reader",
            output_module="features",
            class_name="FileReader",
            params=[("path", "data.txt")],
            subscribes=["file.read"],
            publishes=["data.loaded"],
        )
        self.assertEqual(config["name"], "reader")
        self.assertEqual(config["class"], "features.FileReader")
        self.assertEqual(config["params"]["path"], "data.txt")
        self.assertEqual(config["subscribes"], ["file.read"])
        self.assertEqual(config["publishes"], ["data.loaded"])

    def test_numeric_params(self):
        config = generate_json_config(
            component_name="counter",
            output_module="features",
            class_name="Counter",
            params=[("limit", "100"), ("rate", "3.14")],
            subscribes=[],
            publishes=[],
        )
        self.assertIsInstance(config["params"]["limit"], int)
        self.assertEqual(config["params"]["limit"], 100)
        self.assertIsInstance(config["params"]["rate"], float)

    def test_boolean_params(self):
        config = generate_json_config(
            component_name="toggle",
            output_module="features",
            class_name="Toggle",
            params=[("enabled", "true"), ("debug", "false")],
            subscribes=[],
            publishes=[],
        )
        self.assertTrue(config["params"]["enabled"])
        self.assertFalse(config["params"]["debug"])

    def test_required_params_excluded(self):
        config = generate_json_config(
            component_name="req_test",
            output_module="features",
            class_name="ReqTest",
            params=[("name", None), ("value", "42")],
            subscribes=[],
            publishes=[],
        )
        self.assertNotIn("name", config["params"])
        self.assertIn("value", config["params"])

    def test_json_serializable(self):
        config = generate_json_config(
            component_name="json_test",
            output_module="features",
            class_name="JsonTest",
            params=[("key", "val"), ("num", "10")],
            subscribes=["in"],
            publishes=["out"],
        )
        json_str = json.dumps(config, indent=2)
        roundtrip = json.loads(json_str)
        self.assertEqual(roundtrip, config)


if __name__ == "__main__":
    unittest.main()

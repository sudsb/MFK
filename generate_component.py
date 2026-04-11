"""Interactive CLI script to generate BaseComponent subclass files and JSON config snippets."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
from pathlib import Path
from typing import Any


def handle_interrupt(signum: int, frame: Any) -> None:
    """Handle Ctrl+C gracefully."""
    print("\nComponent generation cancelled.")
    sys.exit(0)


signal.signal(signal.SIGINT, handle_interrupt)


def to_pascal_case(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def validate_identifier(name: str) -> bool:
    """Check if name is a valid Python identifier."""
    return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))


def parse_params(param_lines: list[str]) -> list[tuple[str, str | None]]:
    """Parse key=default pairs into list of (name, default_value_or_None)."""
    params = []
    for line in param_lines:
        line = line.strip()
        if not line:
            continue
        entries = [e.strip() for e in line.split(",") if e.strip()]
        for entry in entries:
            if "=" in entry:
                key, default = entry.split("=", 1)
                key = key.strip()
                default = default.strip()
                if default == "None":
                    params.append((key, None))
                else:
                    params.append((key, default))
            else:
                params.append((entry, None))
    return params


def _format_default_for_code(default: str) -> str:
    """Format a default value for use in Python code."""
    if default.startswith(('"', "'")) and default.endswith(('"', "'")):
        return default
    if default.isdigit() or (default.startswith("-") and default[1:].isdigit()):
        return default
    if default.lower() in ("true", "false") or default == "None":
        return default
    try:
        float(default)
        return default
    except ValueError:
        return f'"{default}"'


def generate_python_code(
    component_name: str,
    description: str,
    subscribes: list[str],
    publishes: list[str],
    params: list[tuple[str, str | None]],
) -> str:
    """Generate the Python component file content."""
    class_name = to_pascal_case(component_name)

    param_list_parts = []
    for key, default in params:
        if default is None:
            param_list_parts.append(f"{key}: Any")
        else:
            formatted = _format_default_for_code(default)
            param_list_parts.append(f"{key}: Any = {formatted}")

    param_str = ", ".join(param_list_parts) if param_list_parts else ""
    if param_str:
        init_signature = f"{param_str}, **kwargs: Any"
    else:
        init_signature = "**kwargs: Any"

    init_body_lines = []
    for key, _default in params:
        init_body_lines.append(f"        self.{key} = {key}")
    init_body_block = "\n".join(init_body_lines) if init_body_lines else "        pass"

    if subscribes:
        subscribe_block = "\n".join(
            f'        self._bus.subscribe("{topic}", self.handle_message)'
            for topic in subscribes
        )
    else:
        subscribe_block = "        pass"

    if publishes:
        publish_topics_str = ", ".join(f'"{t}"' for t in publishes)
        publish_comment = f"        # Publish to: {publish_topics_str}"
    else:
        publish_comment = "        # Publish as needed"

    code = f'''\
"""{description}."""

from __future__ import annotations

from typing import Any

from framework.channels.base import Message
from framework.interfaces import BaseComponent


class {class_name}(BaseComponent):
    """{description}."""

    name: str = "{component_name}"

    def __init__(self, {init_signature}) -> None:
        super().__init__(**kwargs)
{init_body_block}

    def on_start(self) -> None:
        """Subscribe to topics."""
{subscribe_block}

    def handle_message(self, message: Message) -> Any:
        """Process incoming messages."""
        payload = message.payload
        # TODO: Implement message handling logic
{publish_comment}
        pass

    def on_stop(self) -> None:
        """Cleanup resources."""
        pass
'''
    return code


def generate_json_config(
    component_name: str,
    output_module: str,
    class_name: str,
    params: list[tuple[str, str | None]],
    subscribes: list[str],
    publishes: list[str],
) -> dict[str, Any]:
    """Generate the JSON config snippet."""
    param_dict = {}
    for key, default in params:
        if default is not None:
            if default.isdigit():
                param_dict[key] = int(default)
            elif default.lower() in ("true", "false"):
                param_dict[key] = default.lower() == "true"
            elif default.startswith(('"', "'")) and default.endswith(('"', "'")):
                param_dict[key] = default[1:-1]
            else:
                try:
                    param_dict[key] = float(default)
                except ValueError:
                    param_dict[key] = default

    config = {
        "name": component_name,
        "class": f"{output_module}.{class_name}",
        "params": param_dict,
        "subscribes": subscribes,
        "publishes": publishes,
    }
    return config


def ask_questions(output_dir_arg: str | None) -> dict[str, Any]:
    """Run the interactive questionnaire."""
    print("=" * 60)
    print("  Component Generator for MessageBus Framework")
    print("=" * 60)
    print()

    while True:
        name = input("Component name (e.g. data_processor): ").strip()
        if not name:
            print("  Error: Component name cannot be empty.")
            continue
        if not validate_identifier(name):
            print(
                "  Error: Invalid Python identifier. Use letters, numbers, underscores. Must start with letter or underscore."
            )
            continue
        break

    description = input("Short description (e.g. Processes incoming data): ").strip()
    if not description:
        description = f"Component for {name}"

    subs_input = input("Subscribe topics (comma-separated, empty for none): ").strip()
    subscribes = (
        [t.strip() for t in subs_input.split(",") if t.strip()] if subs_input else []
    )

    pubs_input = input("Publish topics (comma-separated, empty for none): ").strip()
    publishes = (
        [t.strip() for t in pubs_input.split(",") if t.strip()] if pubs_input else []
    )

    print(
        "Init parameters (key=default pairs, one per line. 'None' = required, empty line to finish):"
    )
    param_lines = []
    while True:
        line = input("  param> ").strip()
        if not line:
            break
        param_lines.append(line)
    params = parse_params(param_lines)

    default_dir = output_dir_arg if output_dir_arg else "features"
    output_dir = input(f"Output directory (default: {default_dir}): ").strip()
    if not output_dir:
        output_dir = default_dir

    return {
        "component_name": name,
        "description": description,
        "subscribes": subscribes,
        "publishes": publishes,
        "params": params,
        "output_dir": output_dir,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a BaseComponent subclass and JSON config snippet."
    )
    parser.add_argument(
        "-d", "--output-dir", help="Override the output directory prompt", default=None
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated code and JSON without writing files",
    )
    args = parser.parse_args()

    answers = ask_questions(args.output_dir)

    component_name = answers["component_name"]
    description = answers["description"]
    subscribes = answers["subscribes"]
    publishes = answers["publishes"]
    params = answers["params"]
    output_dir = answers["output_dir"]

    class_name = to_pascal_case(component_name)
    filename = f"{component_name}.py"

    python_code = generate_python_code(
        component_name, description, subscribes, publishes, params
    )

    module_path = output_dir.replace(os.sep, ".").rstrip(".")
    json_config = generate_json_config(
        component_name, module_path, class_name, params, subscribes, publishes
    )
    json_str = json.dumps(json_config, indent=2)

    print()
    print("=" * 60)
    print("  PREVIEW: Generated Python Code")
    print("=" * 60)
    print(python_code)
    print()
    print("=" * 60)
    print("  PREVIEW: JSON Config Snippet")
    print("=" * 60)
    print(json_str)
    print()

    if args.dry_run:
        print("[Dry run] No files written.")
        return

    target_dir = Path(output_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"  Error: Cannot create directory '{output_dir}': {e}")
        sys.exit(1)

    target_path = target_dir / filename
    if target_path.exists():
        response = (
            input(f"  Warning: '{target_path}' already exists. Overwrite? (y/N): ")
            .strip()
            .lower()
        )
        if response not in ("y", "yes"):
            print("  Component generation cancelled.")
            return

    target_path.write_text(python_code, encoding="utf-8")
    print(f"  Created: {target_path}")

    json_file = target_dir / f"{component_name}_config.json"
    json_file.write_text(json_str + "\n", encoding="utf-8")
    print(f"  Created: {json_file}")

    print()
    print("  Done! Add the JSON snippet to config.json and import your component.")


if __name__ == "__main__":
    main()

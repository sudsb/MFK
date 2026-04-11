#!/usr/bin/env python3
"""Interactive CLI script to generate config.json for the MessageBus framework."""

import argparse
import json
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate config.json for the MessageBus framework."
    )
    parser.add_argument(
        "-o",
        "--output",
        default="config.json",
        help="Output file path (default: config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON to stdout without writing file",
    )
    return parser.parse_args()


def ask(prompt, default=None):
    """Ask a question and return stripped input, with optional default."""
    if default is not None:
        prompt = f"{prompt} [{default}]: "
    else:
        prompt = f"{prompt}: "
    try:
        value = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nConfiguration generation cancelled.")
        sys.exit(0)
    return value if value else (default or "")


def ask_choice(prompt, choices, default=None):
    """Ask the user to pick from choices. Returns the chosen value."""
    display = ", ".join(choices)
    if default:
        display += f" (default: {default})"
    while True:
        value = ask(f"{prompt} ({display})")
        if not value and default:
            return default
        if value.lower() in choices:
            return value.lower()
        print(f"  Invalid choice. Please choose from: {', '.join(choices)}")


def ask_yes_no(prompt, default="yes"):
    """Ask yes/no question. Returns True/False."""
    hint = "[Y/n]" if default == "yes" else ("[y/N]" if default == "no" else "[y/n]")
    while True:
        value = ask(f"{prompt} {hint}")
        if not value:
            return default == "yes"
        if value.lower() in ("y", "yes"):
            return True
        if value.lower() in ("n", "no"):
            return False
        print("  Please enter 'y' or 'n'.")


def validate_name(name):
    """Validate component name: non-empty, no spaces."""
    if not name:
        print("  Error: Component name cannot be empty.")
        return False
    if " " in name:
        print("  Error: Component name cannot contain spaces.")
        return False
    return True


def validate_class_path(class_path):
    """Validate class path contains a dot (module.Class format)."""
    if "." not in class_path:
        print(
            "  Error: Class path must contain a dot (e.g., 'features.file_reader.FileReader')."
        )
        return False
    return True


def collect_params():
    """Collect key=value parameter pairs from the user."""
    print("  Enter parameters as key=value (one per line, empty line to finish):")
    params = {}
    while True:
        line = ask("  param")
        if not line:
            break
        if "=" not in line:
            print("  Invalid format. Use key=value (e.g., path=sample.txt)")
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if key:
            params[key] = value
    return params


def collect_topics(prompt_text):
    """Collect comma-separated topic strings."""
    while True:
        value = ask(prompt_text)
        if not value:
            return []
        topics = [t.strip() for t in value.split(",") if t.strip()]
        if not topics:
            print(
                "  Topics cannot be empty. Enter comma-separated topics or leave blank for none."
            )
            continue
        return topics


def collect_component():
    """Interactively collect a single component definition."""
    print("\n--- New Component ---")

    while True:
        name = ask("Component name (e.g., reader)")
        if validate_name(name):
            break

    while True:
        class_path = ask("Full class path (e.g., features.file_reader.FileReader)")
        if validate_class_path(class_path):
            break

    params = collect_params()
    subscribes = collect_topics("Subscribe topics (comma-separated, e.g., file.read)")
    publishes = collect_topics("Publish topics (comma-separated, e.g., data.loaded)")

    return {
        "name": name,
        "class": class_path,
        "params": params,
        "subscribes": subscribes,
        "publishes": publishes,
    }


def build_config():
    """Run the interactive config-building flow."""
    print("=" * 60)
    print("  MessageBus Framework - Configuration Generator")
    print("=" * 60)
    print()

    bus_channel = ask_choice(
        "Bus default_channel",
        choices=["normal", "highspeed"],
        default="highspeed",
    )

    components = []
    print()
    if ask_yes_no("Add components?", default="yes"):
        while True:
            comp = collect_component()
            components.append(comp)
            print(f"\n  Component '{comp['name']}' added.")
            if not ask_yes_no("Add another component?", default="no"):
                break

    config = {
        "components": components,
        "bus": {
            "default_channel": bus_channel,
        },
    }
    return config


def preview_config(config):
    """Show JSON preview and ask for confirmation."""
    print("\n" + "=" * 60)
    print("  Generated Configuration:")
    print("=" * 60)
    print(json.dumps(config, indent=2))
    print("=" * 60)

    return ask_yes_no("Write to file?", default="yes")


def main():
    args = parse_args()

    config = build_config()

    if args.dry_run:
        print("\n--- Dry Run Output ---")
        print(json.dumps(config, indent=2))
        print("\n(Dry run: no file written)")
        return

    if not preview_config(config):
        print("Configuration not saved.")
        return

    try:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
    except OSError as e:
        print(f"Error writing file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nConfiguration saved to '{args.output}'.")


if __name__ == "__main__":
    main()

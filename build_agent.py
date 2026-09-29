from pathlib import Path
import argparse
import re
import sys
import yaml


def load_config(config_file: Path):
    with config_file.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    required = [
        "companyName",
        "agentDisplayName",
        "agentComponentName",
        "companySharePointName",
        "companyUrl",
        "sharePointUrl",
        "dynamicsAgentDescription",
    ]

    missing = [key for key in required if not config.get(key)]

    if missing:
        raise RuntimeError(
            "Missing configuration values: " + ", ".join(missing)
        )

    return config


def get_schema_name(settings_file: Path):
    text = settings_file.read_text(encoding="utf-8")

    match = re.search(
        r"(?m)^schemaName:\s*(.+?)\s*$",
        text
    )

    if not match:
        raise RuntimeError(
            f"Could not find schemaName in {settings_file}"
        )

    return match.group(1).strip()


def get_template_type(settings_file: Path):
    text = settings_file.read_text(encoding="utf-8")

    match = re.search(
        r"(?m)^template:\s*(.+?)\s*$",
        text
    )

    if not match:
        return None

    return match.group(1).strip()


def extract_evention_instructions(source_agent_file: Path):
    """
    Extract the multiline instructions block from the classic
    Evention agent.mcs.yml without reserializing Microsoft's YAML.
    """

    text = source_agent_file.read_text(encoding="utf-8")

    match = re.search(
        r"(?ms)^instructions:\s*\|-\s*\n"
        r"(?P<body>.*?)(?=^[A-Za-z][A-Za-z0-9]*:\s*)",
        text,
    )

    if not match:
        # Fallback for instructions block at end of file
        match = re.search(
            r"(?ms)^instructions:\s*\|-\s*\n(?P<body>.*)$",
            text,
        )

    if not match:
        raise RuntimeError(
            f"Could not find instructions block in {source_agent_file}"
        )

    body = match.group("body")

    # Remove the indentation used beneath `instructions: |-`
    lines = body.splitlines()

    cleaned = []

    for line in lines:
        if line.startswith("  "):
            cleaned.append(line[2:])
        else:
            cleaned.append(line)

    return "\n".join(cleaned).rstrip()


def transform_instructions(
    instructions: str,
    source_company: str,
    target_company: str,
):
    """
    Replace explicit references to the template company if any exist.
    Generic instructions remain unchanged.
    """

    if source_company and source_company != target_company:
        instructions = instructions.replace(
            source_company,
            target_company
        )

    return instructions


def update_display_name(
    settings_text: str,
    display_name: str,
):
    new_text, count = re.subn(
        r"(?m)^displayName:\s*.*$",
        f"displayName: {display_name}",
        settings_text,
        count=1,
    )

    if count != 1:
        raise RuntimeError(
            "Could not uniquely update displayName "
            "in target settings.mcs.yml"
        )

    return new_text


def build_instruction_block(instructions: str):
    """
    Build the CLI-agent instruction structure while preserving
    Microsoft's surrounding settings file.
    """

    lines = instructions.splitlines()

    indented_body = "\n".join(
        f"          {line}" if line else ""
        for line in lines
    )

    return (
        "    instructions:\n"
        "      segments:\n"
        "        - kind: StaticSegment\n"
        "          value: |-\n"
        f"{indented_body}"
    )


def replace_instruction_block(
    settings_text: str,
    instructions: str,
):
    """
    Replace either:

        instructions: {}

    or an existing instructions block beneath agentSettings.
    """

    new_block = build_instruction_block(instructions)

    # Most freshly-created CLI agents have this.
    if re.search(
        r"(?m)^    instructions:\s*\{\}\s*$",
        settings_text,
    ):
        return re.sub(
            r"(?m)^    instructions:\s*\{\}\s*$",
            new_block,
            settings_text,
            count=1,
        )

    # Existing generated instructions block.
    pattern = (
        r"(?ms)^    instructions:\s*\n"
        r".*?"
        r"(?=^    [A-Za-z][A-Za-z0-9]*:\s*)"
    )

    if re.search(pattern, settings_text):
        return re.sub(
            pattern,
            new_block + "\n",
            settings_text,
            count=1,
        )

    raise RuntimeError(
        "Could not locate the target instructions section "
        "in settings.mcs.yml"
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Populate a Microsoft-created portfolio agent shell "
            "from the Evention template."
        )
    )

    parser.add_argument(
        "company",
        help="Company config name, e.g. miva"
    )

    parser.add_argument(
        "--source-dir",
        default="Portfolio Analyst Evention",
        help="Source/template agent directory"
    )

    parser.add_argument(
        "--target-dir",
        required=True,
        help="Microsoft-created target agent directory"
    )

    parser.add_argument(
        "--source-company",
        default="Evention",
        help="Company name used by the source template"
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent

    config_file = (
        repo_root
        / "companies"
        / f"{args.company}.yml"
    )

    source_dir = repo_root / args.source_dir
    target_dir = repo_root / args.target_dir

    if not config_file.exists():
        print(f"Config file not found: {config_file}")
        sys.exit(1)

    if not source_dir.exists():
        print(f"Source directory not found: {source_dir}")
        sys.exit(1)

    if not target_dir.exists():
        print(f"Target directory not found: {target_dir}")
        sys.exit(1)

    config = load_config(config_file)

    source_agent_file = source_dir / "agent.mcs.yml"
    target_settings_file = target_dir / "settings.mcs.yml"

    if not source_agent_file.exists():
        raise RuntimeError(
            f"Source agent.mcs.yml not found: {source_agent_file}"
        )

    if not target_settings_file.exists():
        raise RuntimeError(
            f"Target settings.mcs.yml not found: {target_settings_file}"
        )

    schema_name = get_schema_name(target_settings_file)
    template_type = get_template_type(target_settings_file)

    print()
    print("=" * 64)
    print(f"Building {config['agentDisplayName']}")
    print("=" * 64)
    print()
    print(f"Source: {source_dir.name}")
    print(f"Target: {target_dir.name}")
    print(f"Microsoft schema preserved: {schema_name}")
    print(f"Target template: {template_type}")
    print()

    if template_type != "cliagent-1.0.0":
        raise RuntimeError(
            "Target does not appear to be a cliagent-1.0.0 shell. "
            "Stopping rather than modifying an unexpected agent format."
        )

    instructions = extract_evention_instructions(
        source_agent_file
    )

    instructions = transform_instructions(
        instructions,
        args.source_company,
        config["companyName"],
    )

    settings_text = target_settings_file.read_text(
        encoding="utf-8"
    )

    settings_text = update_display_name(
        settings_text,
        config["agentDisplayName"],
    )

    settings_text = replace_instruction_block(
        settings_text,
        instructions,
    )

    target_settings_file.write_text(
        settings_text,
        encoding="utf-8"
    )

    print("Updated:")
    print(f"  displayName -> {config['agentDisplayName']}")
    print(
        f"  instructions -> copied from "
        f"{source_dir.name}/agent.mcs.yml"
    )

    print()
    print("Preserved:")
    print(f"  schemaName -> {schema_name}")
    print(f"  template -> {template_type}")
    print("  authentication configuration")
    print("  model configuration")
    print("  Microsoft-generated agent identity")
    print()

    print("NOT migrated yet:")
    print("  SharePoint knowledge source")
    print("  public website knowledge source")
    print("  Dynamics 365 agent/tool")
    print("  classic topics")
    print("  conversation starters")
    print()
    print("Those require translation from the classic Evention")
    print("agent format into the new CLI-agent format.")
    print()
    print("Build complete.")
    print()


if __name__ == "__main__":
    main()

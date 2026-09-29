from pathlib import Path
import argparse
import re
import sys
import yaml


def replace_first_yaml_value(text, key, value):
    """
    Replace the first YAML key/value occurrence while preserving indentation.
    """
    pattern = rf"(?m)^(\s*{re.escape(key)}:\s*).*$"

    new_text, count = re.subn(
        pattern,
        lambda m: f"{m.group(1)}{value}",
        text,
        count=1
    )

    return new_text, count


def load_config(config_file):
    with config_file.open() as f:
        config = yaml.safe_load(f)

    required = [
        "companyName",
        "agentDisplayName",
        "agentComponentName",
        "companySharePointName",
        "companyUrl",
        "sharePointUrl",
        "schemaName",
        "dynamicsAgentDescription",
    ]

    missing = [
        key for key in required
        if not config.get(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing configuration values: "
            + ", ".join(missing)
        )

    return config


def get_current_schema(settings_file):
    text = settings_file.read_text()

    match = re.search(
        r"(?m)^\s*schemaName:\s*(\S+)\s*$",
        text
    )

    if not match:
        raise RuntimeError(
            f"Could not determine schemaName from {settings_file}"
        )

    return match.group(1)


def update_settings(agent_dir, config):
    settings = agent_dir / "settings.mcs.yml"

    if not settings.exists():
        raise FileNotFoundError(
            f"Could not find {settings}"
        )

    text = settings.read_text()

    text, count = replace_first_yaml_value(
        text,
        "displayName",
        config["agentDisplayName"]
    )

    if count != 1:
        raise RuntimeError(
            "Could not uniquely update displayName "
            "in settings.mcs.yml"
        )

    settings.write_text(text)

    print(
        f"Updated displayName -> "
        f"{config['agentDisplayName']}"
    )


def update_agent_component_name(agent_dir, config):
    agent_file = agent_dir / "agent.mcs.yml"

    if not agent_file.exists():
        print(
            "WARNING: agent.mcs.yml not found."
        )
        return 0

    text = agent_file.read_text()

    new_text, count = re.subn(
        r"(?m)^(\s*componentName:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['agentComponentName']}"
        ),
        text,
        count=1
    )

    if count == 0:
        print(
            "WARNING: componentName not found "
            "in agent.mcs.yml."
        )
        return 0

    agent_file.write_text(new_text)

    print(
        f"Updated agent componentName -> "
        f"{config['agentComponentName']}"
    )

    return 1


def update_dynamics_agent_description(agent_dir, config):
    dynamics_file = (
        agent_dir
        / "agents"
        / "CopilotinDynamics365Sales.mcs.yml"
    )

    if not dynamics_file.exists():
        print(
            "Dynamics 365 Sales agent file not found; "
            "skipping."
        )
        return 0

    text = dynamics_file.read_text()

    text, description_count = re.subn(
        r"(?m)^(\s*description:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['dynamicsAgentDescription']}"
        ),
        text,
        count=1
    )

    text, model_description_count = re.subn(
        r"(?m)^(\s*modelDescription:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['dynamicsAgentDescription']}"
        ),
        text,
        count=1
    )

    if description_count == 0:
        print(
            "WARNING: description not found "
            "in Dynamics agent file."
        )

    if model_description_count == 0:
        print(
            "WARNING: modelDescription not found "
            "in Dynamics agent file."
        )

    dynamics_file.write_text(text)

    print(
        f"Updated Dynamics agent description -> "
        f"{config['dynamicsAgentDescription']}"
    )

    return 1


def update_schema_references(agent_dir, old_schema, new_schema):
    """
    Replace the exact old schema namespace in all source *.mcs.yml files.

    Files inside the hidden/generated .mcs directory are excluded.
    """
    if old_schema == new_schema:
        print(
            f"Schema already correct: {new_schema}"
        )
        return 0

    changed_files = 0

    for file in agent_dir.rglob("*.mcs.yml"):

        if ".mcs" in file.parts:
            continue

        text = file.read_text()

        if old_schema not in text:
            continue

        new_text = text.replace(
            old_schema,
            new_schema
        )

        file.write_text(new_text)

        changed_files += 1

        print(
            f"Updated schema reference: "
            f"{file.relative_to(agent_dir)}"
        )

    print(
        f"Schema namespace: "
        f"{old_schema} -> {new_schema}"
    )

    return changed_files


def rename_schema_files(agent_dir, old_schema, new_schema):
    """
    Rename source files whose filenames contain the old schema namespace.
    """
    if old_schema == new_schema:
        return 0

    files_to_rename = []

    for file in agent_dir.rglob("*"):

        if not file.is_file():
            continue

        if ".mcs" in file.parts:
            continue

        if old_schema in file.name:
            files_to_rename.append(file)

    renamed = 0

    for file in files_to_rename:
        new_name = file.name.replace(
            old_schema,
            new_schema
        )

        new_file = file.with_name(new_name)

        if new_file.exists():
            raise RuntimeError(
                f"Cannot rename {file}; "
                f"destination already exists: {new_file}"
            )

        file.rename(new_file)

        renamed += 1

        print(
            f"Renamed file: "
            f"{file.name} -> {new_file.name}"
        )

    return renamed


def update_sharepoint_knowledge(file, config):
    text = file.read_text()

    if "kind: SharePointSearchSource" not in text:
        return False

    text = re.sub(
        r"(?m)^(\s*componentName:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['companySharePointName']}"
        ),
        text,
        count=1
    )

    description = (
        "This knowledge source provides information found in "
        f"{config['companySharePointName']} SharePoint."
    )

    text = re.sub(
        r"(?m)^(\s*description:\s*).*$",
        lambda m: (
            f"{m.group(1)}{description}"
        ),
        text,
        count=1
    )

    text = re.sub(
        r"(?m)^(\s*site:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['sharePointUrl']}"
        ),
        text,
        count=1
    )

    file.write_text(text)

    print(
        f"Updated SharePoint knowledge: "
        f"{file.name}"
    )

    return True


def update_website_knowledge(file, config):
    text = file.read_text()

    if "kind: PublicSiteSearchSource" not in text:
        return False

    text = re.sub(
        r"(?m)^(\s*componentName:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['companyUrl']}"
        ),
        text,
        count=1
    )

    description = (
        "This knowledge source searches information on the web "
        f"found in {config['companyUrl']} website"
    )

    text = re.sub(
        r"(?m)^(\s*description:\s*).*$",
        lambda m: (
            f"{m.group(1)}{description}"
        ),
        text,
        count=1
    )

    text = re.sub(
        r"(?m)^(\s*site:\s*).*$",
        lambda m: (
            f"{m.group(1)}"
            f"{config['companyUrl']}"
        ),
        text,
        count=1
    )

    file.write_text(text)

    print(
        f"Updated website knowledge: "
        f"{file.name}"
    )

    return True


def update_knowledge_sources(agent_dir, config):
    sharepoint_count = 0
    website_count = 0

    for file in agent_dir.rglob("*.mcs.yml"):

        if ".mcs" in file.parts:
            continue

        if file.name == "settings.mcs.yml":
            continue

        if update_sharepoint_knowledge(
            file,
            config
        ):
            sharepoint_count += 1
            continue

        if update_website_knowledge(
            file,
            config
        ):
            website_count += 1

    return sharepoint_count, website_count


def scan_for_old_company_name(agent_dir, old_company_name):
    """
    Report remaining plain-English references to the source company.
    Does not modify them automatically.
    """
    matches = []

    if not old_company_name:
        return matches

    for file in agent_dir.rglob("*.mcs.yml"):

        if ".mcs" in file.parts:
            continue

        text = file.read_text()

        if old_company_name in text:
            matches.append(
                str(file.relative_to(agent_dir))
            )

    return matches


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build an EAM Copilot Studio "
            "portfolio-company agent."
        )
    )

    parser.add_argument(
        "company",
        help="Company config name, e.g. evention or miva"
    )

    parser.add_argument(
        "--agent-dir",
        required=True,
        help="Path to the copied/cloned Copilot Studio agent"
    )

    parser.add_argument(
        "--source-company",
        default="Evention",
        help=(
            "Original/template company name used only "
            "for leftover-reference reporting. "
            "Default: Evention"
        )
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent

    config_file = (
        repo_root
        / "companies"
        / f"{args.company}.yml"
    )

    agent_dir = (
        repo_root
        / args.agent_dir
    )

    if not config_file.exists():
        print(
            f"Config not found: {config_file}"
        )
        sys.exit(1)

    if not agent_dir.exists():
        print(
            f"Agent directory not found: {agent_dir}"
        )
        sys.exit(1)

    config = load_config(
        config_file
    )

    settings_file = (
        agent_dir
        / "settings.mcs.yml"
    )

    if not settings_file.exists():
        print(
            f"settings.mcs.yml not found in {agent_dir}"
        )
        sys.exit(1)

    old_schema = get_current_schema(
        settings_file
    )

    new_schema = config["schemaName"]

    print()
    print("=" * 60)
    print(
        f"Building agent for "
        f"{config['companyName']}"
    )
    print("=" * 60)
    print()
    print(
        f"Agent directory: "
        f"{agent_dir}"
    )
    print(
        f"Current schema: "
        f"{old_schema}"
    )
    print(
        f"Target schema:  "
        f"{new_schema}"
    )
    print()

    update_settings(
        agent_dir,
        config
    )

    update_agent_component_name(
        agent_dir,
        config
    )

    update_dynamics_agent_description(
        agent_dir,
        config
    )

    schema_changed_files = (
        update_schema_references(
            agent_dir,
            old_schema,
            new_schema
        )
    )

    renamed_files = (
        rename_schema_files(
            agent_dir,
            old_schema,
            new_schema
        )
    )

    sharepoint_count, website_count = (
        update_knowledge_sources(
            agent_dir,
            config
        )
    )

    remaining_company_refs = (
        scan_for_old_company_name(
            agent_dir,
            args.source_company
        )
    )

    print()
    print("=" * 60)
    print("Build complete")
    print("=" * 60)
    print()

    print(
        f"Company: "
        f"{config['companyName']}"
    )
    print(
        f"Agent display name: "
        f"{config['agentDisplayName']}"
    )
    print(
        f"Schema: "
        f"{config['schemaName']}"
    )
    print(
        f"Schema source files changed: "
        f"{schema_changed_files}"
    )
    print(
        f"Schema files renamed: "
        f"{renamed_files}"
    )
    print(
        f"SharePoint knowledge sources updated: "
        f"{sharepoint_count}"
    )
    print(
        f"Website knowledge sources updated: "
        f"{website_count}"
    )

    if sharepoint_count == 0:
        print(
            "WARNING: No SharePoint knowledge source found."
        )

    if website_count == 0:
        print(
            "WARNING: No public website knowledge source found."
        )

    if remaining_company_refs:
        print()
        print(
            f"WARNING: Remaining references to "
            f"'{args.source_company}' found in:"
        )

        for item in remaining_company_refs:
            print(
                f"  - {item}"
            )

        print()
        print(
            "Review those files before creating "
            "the new Copilot Studio agent."
        )

    else:
        print()
        print(
            f"No remaining source-company references "
            f"to '{args.source_company}' found."
        )

    print()


if __name__ == "__main__":
    main()

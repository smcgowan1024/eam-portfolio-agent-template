from pathlib import Path
import argparse
import re
import sys
import yaml


def replace_yaml_value(text, key, value):
    pattern = rf"(?m)^(\s*{re.escape(key)}:\s*).*$"
    new_text, count = re.subn(
        pattern,
        lambda m: f"{m.group(1)}{value}",
        text,
        count=1
    )
    return new_text, count


def update_settings(agent_dir, config):
    settings = agent_dir / "settings.mcs.yml"

    if not settings.exists():
        raise FileNotFoundError(f"Could not find {settings}")

    text = settings.read_text()

    text, count = replace_yaml_value(
        text,
        "displayName",
        config["agentDisplayName"]
    )

    if count != 1:
        raise RuntimeError(
            "Could not uniquely update displayName in settings.mcs.yml")

    settings.write_text(text)

    print(f"Updated agent display name: {settings}")


def update_sharepoint_knowledge(file, config):
    text = file.read_text()

    if "kind: SharePointSearchSource" not in text:
        return False

    # Component name
    text = re.sub(
        r"(?m)^(\s*componentName:\s*).*$",
        lambda m: f"{m.group(1)}{config['companySharePointName']}",
        text,
        count=1
    )

    # Description
    description = (
        f"This knowledge source provides information found in "
        f"{config['companySharePointName']} SharePoint."
    )

    text = re.sub(
        r"(?m)^(\s*description:\s*).*$",
        lambda m: f"{m.group(1)}{description}",
        text,
        count=1
    )

    # Site URL
    text = re.sub(
        r"(?m)^(\s*site:\s*).*$",
        lambda m: f"{m.group(1)}{config['sharePointUrl']}",
        text,
        count=1
    )

    file.write_text(text)

    print(f"Updated SharePoint knowledge: {file}")
    return True


def update_website_knowledge(file, config):
    text = file.read_text()

    if "kind: PublicSiteSearchSource" not in text:
        return False

    # Component name
    text = re.sub(
        r"(?m)^(\s*componentName:\s*).*$",
        lambda m: f"{m.group(1)}{config['companyUrl']}",
        text,
        count=1
    )

    # Description
    description = (
        f"This knowledge source searches information on the web found in "
        f"{config['companyUrl']} website"
    )

    text = re.sub(
        r"(?m)^(\s*description:\s*).*$",
        lambda m: f"{m.group(1)}{description}",
        text,
        count=1
    )

    # Site URL
    text = re.sub(
        r"(?m)^(\s*site:\s*).*$",
        lambda m: f"{m.group(1)}{config['companyUrl']}",
        text,
        count=1
    )

    file.write_text(text)

    print(f"Updated website knowledge: {file}")
    return True


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "company",
        help="Company config name, e.g. evention"
    )

    parser.add_argument(
        "--agent-dir",
        required=True,
        help="Path to cloned Copilot Studio agent"
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent

    config_file = repo_root / "companies" / f"{args.company}.yml"
    agent_dir = repo_root / args.agent_dir

    if not config_file.exists():
        print(f"Config not found: {config_file}")
        sys.exit(1)

    if not agent_dir.exists():
        print(f"Agent directory not found: {agent_dir}")
        sys.exit(1)

    with config_file.open() as f:
        config = yaml.safe_load(f)

    required = [
        "companyName",
        "agentDisplayName",
        "companySharePointName",
        "companyUrl",
        "sharePointUrl",
    ]

    missing = [key for key in required if not config.get(key)]

    if missing:
        raise RuntimeError(
            f"Missing configuration values: {', '.join(missing)}"
        )

    print(f"\nBuilding configuration for {config['companyName']}\n")

    update_settings(agent_dir, config)

    sharepoint_count = 0
    website_count = 0

    for file in agent_dir.rglob("*.mcs.yml"):

        if file.name == "settings.mcs.yml":
            continue

        if update_sharepoint_knowledge(file, config):
            sharepoint_count += 1
            continue

        if update_website_knowledge(file, config):
            website_count += 1

    print("\nDone.")
    print(f"SharePoint knowledge sources updated: {sharepoint_count}")
    print(f"Website knowledge sources updated: {website_count}")

    if sharepoint_count == 0:
        print("WARNING: No SharePoint knowledge source found.")

    if website_count == 0:
        print("WARNING: No website knowledge source found.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml


# ----------------------------------------------------------------------
# Shared Portfolio Analyst instructions
# ----------------------------------------------------------------------

INSTRUCTIONS = [
    "Assist portfolio companies in focusing on key items required for a successful exit.",
    "Provide guidance based on an uploaded file of recommendations.",
    "Ensure companies prioritize critical aspects such as financial readiness, operational efficiency, market positioning, and legal compliance.",
    "Offer strategic insights, practical action steps, and tailored advice.",
    "Reference the uploaded document to provide consistent and relevant recommendations.",
    "Allow for further clarification and discussion as needed.",
    "Support the interactive feature of adding documents for analysis.",
    "Utilize historic monthly and quarterly operational reports to build greater context for the pace of performance.",
    "Gauge if the pace of performance is improving based on the uploaded files.",
    "Periodically incorporate additional files uploaded by the user.",
]


# ----------------------------------------------------------------------
# YAML helpers
# ----------------------------------------------------------------------

def load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a YAML mapping.")

    return data


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000,
        )


# ----------------------------------------------------------------------
# Locate Microsoft-generated files
# ----------------------------------------------------------------------

def find_single_file(agent_dir: Path, filenames: list[str]) -> Path:
    matches = []

    for filename in filenames:
        matches.extend(agent_dir.rglob(filename))

    matches = list(dict.fromkeys(matches))

    if not matches:
        raise FileNotFoundError(
            f"Could not find {' or '.join(filenames)} under {agent_dir}"
        )

    if len(matches) > 1:
        print("Multiple matching files found:")
        for match in matches:
            print(f"  {match}")

        raise RuntimeError(
            f"Expected exactly one matching file under {agent_dir}"
        )

    return matches[0]


# ----------------------------------------------------------------------
# Company configuration
# ----------------------------------------------------------------------

def validate_company_config(config: dict) -> None:
    required_fields = [
        "companyName",
        "agentDisplayName",
        "agentComponentName",
        "companySharePointName",
        "companyUrl",
        "sharePointUrl",
        "dynamicsAgentDescription",
    ]

    missing = [
        field
        for field in required_fields
        if not config.get(field)
    ]

    if missing:
        raise ValueError(
            "Missing required company config fields: "
            + ", ".join(missing)
        )


# ----------------------------------------------------------------------
# Shared sample prompts
# ----------------------------------------------------------------------

def load_sample_prompts(prompt_config: dict) -> list[dict]:
    prompts = prompt_config.get("samplePrompts")

    if not isinstance(prompts, list) or not prompts:
        raise ValueError(
            "shared/sample_prompts.yml must contain "
            "a non-empty 'samplePrompts' list."
        )

    starters = []

    for index, prompt in enumerate(prompts, start=1):

        if isinstance(prompt, dict):
            title = prompt.get("title")
            text = prompt.get("text")

            if not title or not text:
                raise ValueError(
                    f"Sample prompt #{index} must contain "
                    "'title' and 'text'."
                )

            starters.append(
                {
                    "$kind": "ConversationStarter",
                    "title": str(title),
                    "text": str(text),
                }
            )

        elif isinstance(prompt, str):
            prompt_text = prompt.strip()

            if not prompt_text:
                continue

            words = prompt_text.rstrip("?.!").split()
            title = " ".join(words[:6])

            if len(words) > 6:
                title += "..."

            starters.append(
                {
                    "$kind": "ConversationStarter",
                    "title": title,
                    "text": prompt_text,
                }
            )

        else:
            raise ValueError(
                f"Invalid sample prompt #{index}: {prompt}"
            )

    if not starters:
        raise ValueError("No valid sample prompts were found.")

    if len(starters) > 10:
        raise ValueError(
            "Maximum supported sample prompts is 10."
        )

    return starters


# ----------------------------------------------------------------------
# settings.mcs.yml
# ----------------------------------------------------------------------

def update_settings_file(
    settings_path: Path,
    conversation_starters: list[dict],
) -> None:

    settings = load_yaml(settings_path)

    # ------------------------------------------------------------------
    # Remove obsolete root-level model block left by prior builder.
    #
    # In the modern cliagent layout, instructions belong under:
    #
    # configuration:
    #   agentSettings:
    #     instructions:
    #
    # The actual model selection remains under agentSettings.model.
    # ------------------------------------------------------------------

    settings.pop("model", None)

    configuration = settings.setdefault(
        "configuration",
        {}
    )

    agent_settings = configuration.setdefault(
        "agentSettings",
        {}
    )

    # ------------------------------------------------------------------
    # Instructions
    # ------------------------------------------------------------------

    agent_settings["instructions"] = {
        "segments": [
            {
                "kind": "StaticSegment",
                "value": "\n".join(
                    f"- {instruction}"
                    for instruction in INSTRUCTIONS
                ),
            }
        ]
    }

    # ------------------------------------------------------------------
    # Conversation starters
    # ------------------------------------------------------------------

    agent_settings["conversationStarters"] = (
        conversation_starters
    )

    write_yaml(settings_path, settings)

    print("Updated settings:")
    print(f"  {settings_path}")
    print(
        f"  Conversation starters: "
        f"{len(conversation_starters)}"
    )


# ----------------------------------------------------------------------
# SharePoint Knowledge
# ----------------------------------------------------------------------

def create_sharepoint_knowledge(
    agent_dir: Path,
    company_config: dict,
) -> Path:

    # Modern cliagent layout:
    #
    # capabilities/
    #   knowledge/
    #

    knowledge_dir = (
        agent_dir
        / "capabilities"
        / "knowledge"
    )

    knowledge_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    knowledge_path = (
        knowledge_dir
        / "company-sharepoint.mcs.yml"
    )

    knowledge = {
        "mcs.metadata": {
            "componentName": company_config[
                "companySharePointName"
            ],
            "description": (
                f"SharePoint knowledge source for "
                f"{company_config['companyName']}"
            ),
        },
        "kind": "KnowledgeSourceConfiguration",
        "source": {
            "kind": "SharePointSearchSource",
            "site": company_config["sharePointUrl"],
        },
    }

    write_yaml(
        knowledge_path,
        knowledge,
    )

    print("Updated SharePoint knowledge:")
    print(f"  {knowledge_path}")
    print(
        f"  {company_config['sharePointUrl']}"
    )

    return knowledge_path


# ----------------------------------------------------------------------
# Remove legacy knowledge file generated by earlier builder
# ----------------------------------------------------------------------

def remove_legacy_knowledge_file(
    agent_dir: Path,
) -> None:

    legacy_path = (
        agent_dir
        / "knowledge"
        / "company-sharepoint.knowledge.mcs.yml"
    )

    if legacy_path.exists():
        legacy_path.unlink()

        print("Removed legacy knowledge file:")
        print(f"  {legacy_path}")

        legacy_dir = legacy_path.parent

        try:
            legacy_dir.rmdir()
        except OSError:
            pass


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Build a company-specific Portfolio Analyst "
            "from an existing Copilot Studio cliagent workspace."
        )
    )

    parser.add_argument(
        "company",
        help="Company config name. Example: miva",
    )

    parser.add_argument(
        "--agent-dir",
        required=True,
        help=(
            "Existing Microsoft Copilot Studio "
            "agent directory."
        ),
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent

    company_file = (
        repo_root
        / "companies"
        / f"{args.company}.yml"
    )

    sample_prompts_file = (
        repo_root
        / "shared"
        / "sample_prompts.yml"
    )

    agent_dir = (
        repo_root
        / args.agent_dir
    ).resolve()

    # ------------------------------------------------------------------
    # Validate inputs
    # ------------------------------------------------------------------

    if not agent_dir.exists():
        raise FileNotFoundError(
            f"Agent directory not found: {agent_dir}"
        )

    company_config = load_yaml(
        company_file
    )

    validate_company_config(
        company_config
    )

    sample_prompt_config = load_yaml(
        sample_prompts_file
    )

    conversation_starters = load_sample_prompts(
        sample_prompt_config
    )

    # ------------------------------------------------------------------
    # Locate settings file
    # ------------------------------------------------------------------

    settings_path = find_single_file(
        agent_dir,
        [
            "settings.mcs.yml",
            "settings.mcs.yaml",
        ],
    )

    # ------------------------------------------------------------------
    # Apply template
    # ------------------------------------------------------------------

    update_settings_file(
        settings_path,
        conversation_starters,
    )

    remove_legacy_knowledge_file(
        agent_dir,
    )

    create_sharepoint_knowledge(
        agent_dir,
        company_config,
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)

    print(
        f"Company:      "
        f"{company_config['companyName']}"
    )

    print(
        f"Agent:        "
        f"{company_config['agentDisplayName']}"
    )

    print(
        f"Prompts:      "
        f"{len(conversation_starters)}"
    )

    print(
        f"SharePoint:   "
        f"{company_config['sharePointUrl']}"
    )

    print()
    print("agent.sync.yaml was not modified.")
    print("Root-level model.instructions was removed.")
    print("Knowledge written under capabilities/knowledge/.")
    print()
    print("Next:")
    print("  git status")
    print("  git diff")
    print()
    print(
        "Review the diff before committing or "
        "pushing to Copilot Studio."
    )


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------

if __name__ == "__main__":

    try:
        main()

    except Exception as exc:

        print()
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )

        sys.exit(1)

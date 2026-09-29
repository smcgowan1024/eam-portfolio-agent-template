from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml


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


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------

def validate_company_config(config: dict) -> None:
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
        raise ValueError(
            "Missing company configuration fields: "
            + ", ".join(missing)
        )


def validate_defaults(defaults: dict) -> None:
    if not defaults.get("description"):
        raise ValueError(
            "shared/agent_defaults.yml is missing 'description'."
        )

    instructions = defaults.get("instructions")

    if not isinstance(instructions, list) or not instructions:
        raise ValueError(
            "shared/agent_defaults.yml must contain "
            "a non-empty 'instructions' list."
        )


# ----------------------------------------------------------------------
# Shared prompts
# ----------------------------------------------------------------------

def load_sample_prompts(prompt_config: dict) -> list[dict]:
    prompts = prompt_config.get("samplePrompts")

    if not isinstance(prompts, list) or not prompts:
        raise ValueError(
            "shared/sample_prompts.yml must contain "
            "a non-empty 'samplePrompts' list."
        )

    result = []

    for index, prompt in enumerate(prompts, start=1):

        if isinstance(prompt, dict):
            title = prompt.get("title")
            text = prompt.get("text")

            if not title or not text:
                raise ValueError(
                    f"Prompt #{index} must contain title and text."
                )

            result.append(
                {
                    "title": str(title),
                    "text": str(text),
                }
            )

        elif isinstance(prompt, str):
            text = prompt.strip()

            if not text:
                continue

            words = text.rstrip("?.!").split()
            title = " ".join(words[:6])

            if len(words) > 6:
                title += "..."

            result.append(
                {
                    "title": title,
                    "text": text,
                }
            )

        else:
            raise ValueError(
                f"Invalid sample prompt #{index}: {prompt}"
            )

    if not result:
        raise ValueError("No valid suggested prompts found.")

    return result


# ----------------------------------------------------------------------
# Standard agent.mcs.yml
# ----------------------------------------------------------------------

def update_agent(
    agent_path: Path,
    company_config: dict,
    defaults: dict,
    sample_prompts: list[dict],
) -> None:

    agent = load_yaml(agent_path)

    # --------------------------------------------------------------
    # Remove any stale root-level description from earlier builds.
    # Working Evention schema proves description belongs under
    # mcs.metadata.
    # --------------------------------------------------------------

    agent.pop("description", None)

    # --------------------------------------------------------------
    # Metadata
    # --------------------------------------------------------------

    metadata = agent.setdefault("mcs.metadata", {})

    metadata["componentName"] = (
        company_config["agentComponentName"]
    )

    metadata["description"] = str(
        defaults["description"]
    ).strip()

    # --------------------------------------------------------------
    # Component type
    # --------------------------------------------------------------

    agent["kind"] = "GptComponentMetadata"

    # --------------------------------------------------------------
    # Instructions
    # --------------------------------------------------------------

    agent["instructions"] = "\n".join(
        f"- {instruction}"
        for instruction in defaults["instructions"]
    )

    # --------------------------------------------------------------
    # GPT capabilities
    #
    # Preserve whatever the target Standard agent already has.
    # --------------------------------------------------------------

    if "gptCapabilities" not in agent:
        agent["gptCapabilities"] = {}

    # --------------------------------------------------------------
    # Conversation starters
    # --------------------------------------------------------------

    agent["conversationStarters"] = [
        {
            "title": prompt["title"],
            "text": prompt["text"],
        }
        for prompt in sample_prompts
    ]

    # --------------------------------------------------------------
    # Model settings
    #
    # Preserve Microsoft-generated model choice.
    # --------------------------------------------------------------

    if "aISettings" not in agent:
        agent["aISettings"] = {
            "model": {}
        }

    write_yaml(agent_path, agent)

    print("Updated Standard agent:")
    print(f"  {agent_path}")
    print("  Description: yes")
    print(
        f"  Instructions: "
        f"{len(defaults['instructions'])}"
    )
    print(
        f"  Suggested prompts: "
        f"{len(sample_prompts)}"
    )


# ----------------------------------------------------------------------
# Knowledge helpers
# ----------------------------------------------------------------------

def find_template_knowledge_file(
    template_dir: Path,
    source_kind: str,
) -> Path:

    knowledge_dir = template_dir / "knowledge"

    if not knowledge_dir.exists():
        raise FileNotFoundError(
            f"Template knowledge folder not found: "
            f"{knowledge_dir}"
        )

    for path in knowledge_dir.glob("*.mcs.yml"):

        data = load_yaml(path)

        source = data.get("source", {})

        if source.get("kind") == source_kind:
            return path

    raise FileNotFoundError(
        f"Could not find Evention knowledge template "
        f"with source kind {source_kind}"
    )


def build_sharepoint_knowledge(
    template_dir: Path,
    target_dir: Path,
    company_config: dict,
) -> None:

    template_path = find_template_knowledge_file(
        template_dir,
        "SharePointSearchSource",
    )

    knowledge = load_yaml(template_path)

    metadata = knowledge.setdefault(
        "mcs.metadata",
        {}
    )

    metadata["componentName"] = (
        company_config["companySharePointName"]
    )

    metadata["description"] = (
        f"This knowledge source provides information "
        f"found in {company_config['companyName']} SharePoint."
    )

    source = knowledge.setdefault("source", {})

    source["kind"] = "SharePointSearchSource"
    source["site"] = company_config["sharePointUrl"]

    destination = (
        target_dir
        / "knowledge"
        / "company-sharepoint.mcs.yml"
    )

    write_yaml(destination, knowledge)

    print("Updated SharePoint knowledge:")
    print(f"  {destination}")


def build_website_knowledge(
    template_dir: Path,
    target_dir: Path,
    company_config: dict,
) -> None:

    template_path = find_template_knowledge_file(
        template_dir,
        "PublicSiteSearchSource",
    )

    knowledge = load_yaml(template_path)

    if isinstance(knowledge.get("mcs.metadata"), dict):
        knowledge["mcs.metadata"]["componentName"] = (
            f"{company_config['companyName']} Website"
        )

        knowledge["mcs.metadata"]["description"] = (
            f"Public website knowledge source for "
            f"{company_config['companyName']}."
        )

    source = knowledge.setdefault("source", {})

    source["kind"] = "PublicSiteSearchSource"
    source["site"] = company_config["companyUrl"]

    destination = (
        target_dir
        / "knowledge"
        / "company-website.mcs.yml"
    )

    write_yaml(destination, knowledge)

    print("Updated website knowledge:")
    print(f"  {destination}")


# ----------------------------------------------------------------------
# Dynamics connected agent
# ----------------------------------------------------------------------

def build_dynamics_agent(
    template_dir: Path,
    target_dir: Path,
    company_config: dict,
) -> None:

    source_path = (
        template_dir
        / "agents"
        / "CopilotinDynamics365Sales.mcs.yml"
    )

    destination = (
        target_dir
        / "agents"
        / "CopilotinDynamics365Sales.mcs.yml"
    )

    content = read_text(source_path)

    replacements = {
        "Dynamics Agent for Evention":
            company_config["dynamicsAgentDescription"],

        "Portfolio Analyst Evention":
            company_config["agentDisplayName"],

        "Evention":
            company_config["companyName"],
    }

    for old, new in replacements.items():
        content = content.replace(old, new)

    write_text(destination, content)

    print("Updated Dynamics connected agent:")
    print(f"  {destination}")


# ----------------------------------------------------------------------
# Connection references
# ----------------------------------------------------------------------

def copy_connection_references(
    template_dir: Path,
    target_dir: Path,
) -> None:

    source = (
        template_dir
        / "connectionreferences.mcs.yml"
    )

    destination = (
        target_dir
        / "connectionreferences.mcs.yml"
    )

    if not source.exists():
        print("No connection references found; skipping.")
        return

    shutil.copyfile(source, destination)

    print("Copied connection references:")
    print(f"  {destination}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Build an EAM Portfolio Analyst using "
            "the Standard Copilot Studio harness."
        )
    )

    parser.add_argument(
        "company",
        help="Company configuration name, e.g. miva",
    )

    parser.add_argument(
        "--agent-dir",
        required=True,
        help="Existing Standard Copilot Studio agent directory.",
    )

    parser.add_argument(
        "--template-dir",
        default="Portfolio Analyst Evention",
        help=(
            "Working Standard template agent. "
            'Default: "Portfolio Analyst Evention"'
        ),
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent

    company_file = (
        repo_root
        / "companies"
        / f"{args.company}.yml"
    )

    defaults_file = (
        repo_root
        / "shared"
        / "agent_defaults.yml"
    )

    prompts_file = (
        repo_root
        / "shared"
        / "sample_prompts.yml"
    )

    target_dir = (
        repo_root
        / args.agent_dir
    ).resolve()

    template_dir = (
        repo_root
        / args.template_dir
    ).resolve()

    # ------------------------------------------------------------------
    # Validate target
    # ------------------------------------------------------------------

    if not target_dir.exists():
        raise FileNotFoundError(
            f"Target agent directory not found: {target_dir}"
        )

    if not template_dir.exists():
        raise FileNotFoundError(
            f"Template agent directory not found: {template_dir}"
        )

    agent_path = (
        target_dir
        / "agent.mcs.yml"
    )

    if not agent_path.exists():
        raise FileNotFoundError(
            "This does not appear to be a Standard agent. "
            f"agent.mcs.yml was not found under {target_dir}"
        )

    # ------------------------------------------------------------------
    # Load configuration
    # ------------------------------------------------------------------

    company_config = load_yaml(
        company_file
    )

    defaults = load_yaml(
        defaults_file
    )

    prompt_config = load_yaml(
        prompts_file
    )

    validate_company_config(
        company_config
    )

    validate_defaults(
        defaults
    )

    sample_prompts = load_sample_prompts(
        prompt_config
    )

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    update_agent(
        agent_path,
        company_config,
        defaults,
        sample_prompts,
    )

    build_sharepoint_knowledge(
        template_dir,
        target_dir,
        company_config,
    )

    build_website_knowledge(
        template_dir,
        target_dir,
        company_config,
    )

    build_dynamics_agent(
        template_dir,
        target_dir,
        company_config,
    )

    copy_connection_references(
        template_dir,
        target_dir,
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    print()
    print("=" * 64)
    print("STANDARD PORTFOLIO ANALYST BUILD COMPLETE")
    print("=" * 64)

    print(
        f"Company:           "
        f"{company_config['companyName']}"
    )

    print(
        f"Agent:             "
        f"{company_config['agentDisplayName']}"
    )

    print(
        f"Instructions:      "
        f"{len(defaults['instructions'])}"
    )

    print(
        f"Suggested prompts: "
        f"{len(sample_prompts)}"
    )

    print()
    print("Description written to mcs.metadata.description.")
    print("Stale root-level description removed.")
    print("Conversation starters written to agent.mcs.yml.")
    print("Existing model selection preserved.")
    print()
    print("Next:")
    print("  git status")
    print("  git diff")


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

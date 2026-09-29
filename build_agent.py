from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

import yaml


# ----------------------------------------------------------------------
# Shared Portfolio Analyst instructions
# ----------------------------------------------------------------------

INSTRUCTIONS = [
    "Assist portfolio companies in focusing on key items required for a successful exit.",
    "Provide guidance based on uploaded recommendations and company materials.",
    "Ensure companies prioritize critical aspects such as financial readiness, operational efficiency, market positioning, and legal compliance.",
    "Offer strategic insights, practical action steps, and tailored advice.",
    "Reference available company documents to provide consistent and relevant recommendations.",
    "Allow for further clarification and discussion as needed.",
    "Support interactive analysis of documents provided by the user.",
    "Utilize historic monthly and quarterly operational reports to build context for the pace of performance.",
    "Gauge whether the pace of performance is improving based on available historical materials.",
    "Incorporate additional company materials as they become available.",
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


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ----------------------------------------------------------------------
# Company config
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
            "Missing required company config fields: "
            + ", ".join(missing)
        )


# ----------------------------------------------------------------------
# Shared prompts
# ----------------------------------------------------------------------

def load_sample_prompts(prompt_config: dict) -> list[dict]:
    prompts = prompt_config.get("samplePrompts")

    if not isinstance(prompts, list) or not prompts:
        raise ValueError(
            "shared/sample_prompts.yml must contain "
            "a non-empty samplePrompts list."
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

    return result


# ----------------------------------------------------------------------
# Standard agent.mcs.yml
# ----------------------------------------------------------------------

def update_standard_agent(
    agent_path: Path,
    company_config: dict,
    sample_prompts: list[dict],
) -> None:

    agent = load_yaml(agent_path)

    # Preserve Microsoft-generated schemaName and identity.
    # Only change the fields we own.

    if "displayName" in agent:
        agent["displayName"] = company_config["agentDisplayName"]

    if "description" in agent:
        agent["description"] = (
            f"Portfolio analyst for {company_config['companyName']}."
        )

    # Standard agents store authored instructions here.
    agent["instructions"] = "\n".join(
        f"- {instruction}"
        for instruction in INSTRUCTIONS
    )

    # Standard conversation starters.
    starters = []

    for prompt in sample_prompts:
        starters.append(
            {
                "title": prompt["title"],
                "text": prompt["text"],
            }
        )

    agent["conversationStarters"] = starters

    write_yaml(agent_path, agent)

    print(f"Updated Standard agent:")
    print(f"  {agent_path}")
    print(f"  Prompts: {len(starters)}")


# ----------------------------------------------------------------------
# Token substitution for proven Evention components
# ----------------------------------------------------------------------

def substitute_evention_values(
    content: str,
    company_config: dict,
) -> str:

    company = company_config["companyName"]
    display_name = company_config["agentDisplayName"]
    component_name = company_config["agentComponentName"]
    sharepoint_name = company_config["companySharePointName"]
    company_url = company_config["companyUrl"]
    sharepoint_url = company_config["sharePointUrl"]
    dynamics_description = company_config["dynamicsAgentDescription"]

    replacements = {
        "Portfolio Analyst Evention": display_name,
        "PortfolioAnalystEvention": component_name.replace(" ", ""),
        "portfolioAnalystEvention": component_name.replace(" ", ""),
        "portfolioanalystevention": component_name.replace(" ", "").lower(),
        "Evention NEW": sharepoint_name,
        "Evention": company,
        "https://www.eventionllc.com/": company_url,
        "https://www.eventionllc.com": company_url.rstrip("/"),
        "Dynamics Agent for Evention": dynamics_description,
    }

    for old, new in replacements.items():
        content = content.replace(old, new)

    # Replace any Evention SharePoint URL with the company SharePoint URL.
    content = re.sub(
        r"https://equalityam\.sharepoint\.com/[^\s'\"<>]+Evention[^\s'\"<>]*",
        sharepoint_url,
        content,
        flags=re.IGNORECASE,
    )

    return content


# ----------------------------------------------------------------------
# Copy proven Evention Standard components
# ----------------------------------------------------------------------

def copy_evention_component(
    source: Path,
    destination: Path,
    company_config: dict,
) -> None:

    content = read_text(source)

    updated = substitute_evention_values(
        content,
        company_config,
    )

    write_text(
        destination,
        updated,
    )

    print(f"Created:")
    print(f"  {destination}")


def build_standard_components(
    evention_dir: Path,
    target_dir: Path,
    company_config: dict,
) -> None:

    # ------------------------------------------------------------------
    # Dynamics connected agent
    # ------------------------------------------------------------------

    source_dynamics = (
        evention_dir
        / "agents"
        / "CopilotinDynamics365Sales.mcs.yml"
    )

    target_dynamics = (
        target_dir
        / "agents"
        / "CopilotinDynamics365Sales.mcs.yml"
    )

    copy_evention_component(
        source_dynamics,
        target_dynamics,
        company_config,
    )

    # ------------------------------------------------------------------
    # Connection references
    # ------------------------------------------------------------------

    source_connections = (
        evention_dir
        / "connectionreferences.mcs.yml"
    )

    target_connections = (
        target_dir
        / "connectionreferences.mcs.yml"
    )

    copy_evention_component(
        source_connections,
        target_connections,
        company_config,
    )

    # ------------------------------------------------------------------
    # Knowledge
    #
    # Use the known-good Evention knowledge files as templates.
    # ------------------------------------------------------------------

    source_knowledge_dir = (
        evention_dir
        / "knowledge"
    )

    target_knowledge_dir = (
        target_dir
        / "knowledge"
    )

    target_knowledge_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    knowledge_files = sorted(
        source_knowledge_dir.glob("*.mcs.yml")
    )

    if not knowledge_files:
        raise FileNotFoundError(
            f"No Evention knowledge files found under "
            f"{source_knowledge_dir}"
        )

    for index, source_file in enumerate(
        knowledge_files,
        start=1,
    ):

        content = read_text(source_file)

        updated = substitute_evention_values(
            content,
            company_config,
        )

        # Keep generated component identifiers out of the filename.
        # Use predictable company-neutral local filenames.
        lower = updated.lower()

        if "sharepointsearchsource" in lower:
            filename = "company-sharepoint.mcs.yml"

        elif (
            "publicsitesearchsource" in lower
            or company_config["companyUrl"].lower() in lower
        ):
            filename = "company-website.mcs.yml"

        else:
            filename = f"knowledge-{index}.mcs.yml"

        destination = (
            target_knowledge_dir
            / filename
        )

        write_text(
            destination,
            updated,
        )

        print(f"Created:")
        print(f"  {destination}")


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> None:

    parser = argparse.ArgumentParser(
        description=(
            "Build a Standard Copilot Studio Portfolio Analyst "
            "using the working Evention Standard agent as the template."
        )
    )

    parser.add_argument(
        "company",
        help="Company config name, for example: miva",
    )

    parser.add_argument(
        "--agent-dir",
        required=True,
        help=(
            "Fresh Standard target agent directory, "
            'for example "Portfolio Analyst Miva"'
        ),
    )

    parser.add_argument(
        "--template-dir",
        default="Portfolio Analyst Evention",
        help=(
            "Working Standard template agent directory. "
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

    prompts_file = (
        repo_root
        / "shared"
        / "sample_prompts.yml"
    )

    target_dir = (
        repo_root
        / args.agent_dir
    ).resolve()

    evention_dir = (
        repo_root
        / args.template_dir
    ).resolve()

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    if not target_dir.exists():
        raise FileNotFoundError(
            f"Target agent directory not found: {target_dir}"
        )

    if not evention_dir.exists():
        raise FileNotFoundError(
            f"Evention template directory not found: {evention_dir}"
        )

    company_config = load_yaml(
        company_file
    )

    validate_company_config(
        company_config
    )

    prompt_config = load_yaml(
        prompts_file
    )

    sample_prompts = load_sample_prompts(
        prompt_config
    )

    target_agent_file = (
        target_dir
        / "agent.mcs.yml"
    )

    if not target_agent_file.exists():
        raise FileNotFoundError(
            f"Fresh Standard agent.mcs.yml not found: "
            f"{target_agent_file}"
        )

    # ------------------------------------------------------------------
    # Update the fresh Standard shell
    # ------------------------------------------------------------------

    update_standard_agent(
        target_agent_file,
        company_config,
        sample_prompts,
    )

    # ------------------------------------------------------------------
    # Copy only proven Evention Standard components
    # ------------------------------------------------------------------

    build_standard_components(
        evention_dir,
        target_dir,
        company_config,
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    print()
    print("=" * 60)
    print("STANDARD PORTFOLIO ANALYST BUILD COMPLETE")
    print("=" * 60)

    print(
        f"Company:     "
        f"{company_config['companyName']}"
    )

    print(
        f"Agent:       "
        f"{company_config['agentDisplayName']}"
    )

    print(
        f"Prompts:     "
        f"{len(sample_prompts)}"
    )

    print(
        f"SharePoint:  "
        f"{company_config['sharePointUrl']}"
    )

    print(
        f"Website:     "
        f"{company_config['companyUrl']}"
    )

    print()
    print("Standard system topics were left untouched.")
    print("Miva schema/identity in agent.mcs.yml was preserved.")
    print("Evention Standard components were used as templates.")
    print()
    print("Next:")
    print("  git status")
    print("  git diff")
    print()
    print(
        "Review the generated files before applying "
        "changes to Copilot Studio."
    )


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

"""Parse the curated store policy manual into sections the agent can look up."""
import re
from dataclasses import dataclass

SECTION_SLUGS = {
    1: "about_store",
    2: "opening_hours",
    3: "payment",
    4: "returns_and_exchanges",
    5: "shipping",
    6: "promotions",
    7: "customer_service",
    8: "warranty",
    9: "privacy",
    10: "final_provisions",
}

SECTION_HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)


class PolicyParseError(Exception):
    pass


@dataclass(frozen=True)
class PolicySection:
    slug: str
    number: int
    title: str
    content: str


def parse_policies(markdown: str) -> list[PolicySection]:
    headings = list(SECTION_HEADING.finditer(markdown))
    sections = []
    for index, match in enumerate(headings):
        number = int(match.group(1))
        if number not in SECTION_SLUGS:
            raise PolicyParseError(f"Unexpected policy section number: {number}")
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        sections.append(
            PolicySection(
                slug=SECTION_SLUGS[number],
                number=number,
                title=match.group(2).strip(),
                content=markdown[match.end():end].strip(),
            )
        )

    missing = set(SECTION_SLUGS) - {section.number for section in sections}
    if missing:
        raise PolicyParseError(f"Missing policy sections: {sorted(missing)}")
    return sections

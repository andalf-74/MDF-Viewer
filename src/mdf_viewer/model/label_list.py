"""Label list parsing/serialization — Vector CANape-style `.lab` files (#143).

Pure data: no UI/Qt/asammdf knowledge. A label list is a group-based,
line-oriented plain-text format: a fixed `[Measurement]` header line,
followed by any number of `[Group Name]` sections each listing one signal
name per line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mdf_viewer.errors import LabelListParseError

_HEADER_LINE = "[Measurement]"
_GROUP_HEADER_RE = re.compile(r"^\[(.*)\]$")


@dataclass
class LabelGroup:
    """One named group of candidate signal names from a label list file.

    `name` is None for the "ungrouped" pseudo-group of names that appear
    directly after `[Measurement]` with no `[Group]` header of their own
    (#175) — those route to the active stripe on import instead of a new,
    group-named stripe.
    """

    name: str | None
    signal_names: list[str] = field(default_factory=list)


def parse_label_list(data: bytes) -> list[LabelGroup]:
    """Parse the bytes of a `.lab` file into its groups.

    Decodes as UTF-8, falling back to Windows-1252 (near-universally
    decodable) if that fails, so legacy CANape exports still load
    (REQ-LABEL-020). Raises LabelListParseError if the file is empty or its
    first line is not exactly "[Measurement]" (REQ-LABEL-010).

    A candidate signal name appearing directly after "[Measurement]", before
    any "[Group]" header, is collected into a leading ungrouped LabelGroup
    (name=None) rather than dropped (REQ-LABEL-014).
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("cp1252")

    lines = text.splitlines()
    if not lines or lines[0] != _HEADER_LINE:
        raise LabelListParseError(
            "This doesn't look like a Label List file — expected "
            f'"{_HEADER_LINE}" on the first line.'
        )

    groups: list[LabelGroup] = []
    ungrouped = LabelGroup(name=None)
    current: LabelGroup | None = None
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue
        match = _GROUP_HEADER_RE.match(stripped)
        if match:
            current = LabelGroup(name=match.group(1))
            groups.append(current)
        elif current is not None:
            current.signal_names.append(stripped)
        else:
            ungrouped.signal_names.append(stripped)
    if ungrouped.signal_names:
        groups.insert(0, ungrouped)
    return groups


def format_label_list(groups: list[LabelGroup]) -> bytes:
    """Serialize *groups* back into `.lab` file bytes, UTF-8 encoded
    (REQ-LABEL-021). Groups with no signal names are omitted."""
    lines = [_HEADER_LINE]
    for group in groups:
        if not group.signal_names:
            continue
        lines.append("")
        lines.append(f"[{group.name}]")
        lines.extend(group.signal_names)
    return ("\n".join(lines) + "\n").encode("utf-8")

"""Tests for label_list.py — parsing/serializing .lab label list files (#143)."""

from __future__ import annotations

import pytest

from mdf_viewer.errors import LabelListParseError
from mdf_viewer.model.label_list import LabelGroup, format_label_list, parse_label_list


@pytest.mark.requirement("REQ-LABEL-010")
def test_parse_rejects_missing_header() -> None:
    with pytest.raises(LabelListParseError):
        parse_label_list(b"[Not A Measurement]\n[Group]\nSignalA\n")


@pytest.mark.requirement("REQ-LABEL-010")
def test_parse_rejects_empty_file() -> None:
    with pytest.raises(LabelListParseError):
        parse_label_list(b"")


@pytest.mark.requirement("REQ-LABEL-010")
def test_parse_accepts_header_only_file() -> None:
    assert parse_label_list(b"[Measurement]\n") == []


@pytest.mark.requirement("REQ-LABEL-011")
def test_parse_splits_into_groups() -> None:
    data = b"[Measurement]\n[Group One]\nSignalA\nSignalB\n\n[Group Two]\nSignalC\n"
    groups = parse_label_list(data)
    assert groups == [
        LabelGroup(name="Group One", signal_names=["SignalA", "SignalB"]),
        LabelGroup(name="Group Two", signal_names=["SignalC"]),
    ]


@pytest.mark.requirement("REQ-LABEL-011")
def test_parse_keeps_nested_brackets_in_group_name_verbatim() -> None:
    data = b"[Measurement]\n[Helper Values for Command[...] ]\nSignalA\n"
    groups = parse_label_list(data)
    assert groups[0].name == "Helper Values for Command[...] "


@pytest.mark.requirement("REQ-LABEL-012")
@pytest.mark.requirement("REQ-LABEL-013")
def test_blank_line_and_next_header_both_end_a_group() -> None:
    data = b"[Measurement]\n[Group One]\nSignalA\n\n[Group Two]\nSignalB\nSignalC\n"
    groups = parse_label_list(data)
    assert groups[0].signal_names == ["SignalA"]
    assert groups[1].signal_names == ["SignalB", "SignalC"]


def test_parse_handles_crlf_line_endings() -> None:
    data = b"[Measurement]\r\n[Group]\r\nSignalA\r\nSignalB\r\n"
    groups = parse_label_list(data)
    assert groups == [LabelGroup(name="Group", signal_names=["SignalA", "SignalB"])]


def test_parse_handles_bare_cr_line_endings() -> None:
    data = b"[Measurement]\r[Group]\rSignalA\r"
    groups = parse_label_list(data)
    assert groups == [LabelGroup(name="Group", signal_names=["SignalA"])]


@pytest.mark.requirement("REQ-LABEL-020")
def test_parse_decodes_utf8() -> None:
    data = "[Measurement]\n[Größen]\nSignalA\n".encode("utf-8")
    groups = parse_label_list(data)
    assert groups[0].name == "Größen"


@pytest.mark.requirement("REQ-LABEL-020")
def test_parse_falls_back_to_cp1252_on_invalid_utf8() -> None:
    data = "[Measurement]\n[Größen]\nSignalA\n".encode("cp1252")
    groups = parse_label_list(data)
    assert groups[0].name == "Größen"


@pytest.mark.requirement("REQ-LABEL-021")
def test_format_writes_header_and_groups() -> None:
    groups = [
        LabelGroup(name="Group One", signal_names=["SignalA", "SignalB"]),
        LabelGroup(name="Group Two", signal_names=["SignalC"]),
    ]
    data = format_label_list(groups)
    assert data.decode("utf-8") == (
        "[Measurement]\n\n[Group One]\nSignalA\nSignalB\n\n[Group Two]\nSignalC\n"
    )


@pytest.mark.requirement("REQ-LABEL-021")
def test_format_omits_groups_with_no_signals() -> None:
    groups = [LabelGroup(name="Empty", signal_names=[]), LabelGroup(name="Full", signal_names=["SignalA"])]
    data = format_label_list(groups)
    assert b"Empty" not in data
    assert b"[Full]" in data


def test_round_trip_format_then_parse() -> None:
    original = [
        LabelGroup(name="Group One", signal_names=["SignalA", "SignalB"]),
        LabelGroup(name="Group Two", signal_names=["SignalC"]),
    ]
    assert parse_label_list(format_label_list(original)) == original

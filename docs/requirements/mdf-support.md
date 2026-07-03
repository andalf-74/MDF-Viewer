# Requirements: MDF Support

Part of the `docs/requirements/` collection (see CLAUDE.md's "Requirements
Workflow" for conventions and ID scheme). This file covers what the
application can read out of an MDF3/MDF4 file: channel discovery, signal
sample loading, metadata, and resilience to malformed content.

**Out of scope here:** the single-file-at-a-time opening/replacing
workflow (`file-handling.md`), and how discovered channels are presented
on screen — e.g. the Signal Browser tree widget (`docs/ui.md`).

---

## Supported File Types

The application reads MDF3 and MDF4 measurement files [REQ-MDF-010].

## Channel Group / Channel Discovery

Opening a measurement exposes its complete channel group and channel
hierarchy: every channel group in the file, and every channel within each
group, is enumerated and made available for browsing — none are filtered
out at load time [REQ-MDF-020]. Each channel group has a display name
derived from the group's acquisition name (MDF4) or comment (MDF3),
falling back to a generic "Group N" label when neither is present
[REQ-MDF-021]. Discovery exposes channel metadata only (name, unit,
comment, its location within the file) and does not load sample data, so
opening a file with many channels does not require reading every
channel's samples upfront [REQ-MDF-022].

## Loading Signal Samples

Sample data for a channel is loaded on demand, one channel at a time, when
the user adds it to the plot — not eagerly for the whole file
[REQ-MDF-030]. Loaded samples are converted to numeric (float64)
timestamps and values regardless of the channel's original storage type
[REQ-MDF-031]. Channels whose raw values are not directly numeric (e.g.
string- or enum-backed channels) are retried using the channel's raw,
unconverted values before giving up [REQ-MDF-032]; if the samples still
cannot be represented numerically, loading that channel fails with an
error rather than silently producing incorrect data [REQ-MDF-033]. A
channel already active in the plot is not loaded a second time when
re-added [REQ-MDF-034].

## Signal Metadata

For a loaded channel the application exposes: its name, unit, and
comment; sample count; minimum and maximum sample value; the channel
group and channel indices identifying its location in the file; the
original (pre-conversion) data type and whether it was an integer type;
and, when the channel has a fixed sampling interval, that raster in
seconds — a variable or indeterminate interval is represented as unknown
rather than guessed [REQ-MDF-040]. A channel using an MDF4 "value to
text" conversion also exposes a mapping from raw integer sample values to
their display labels [REQ-MDF-041].

## Measurement (File-Level) Metadata

Opening a file exposes file-level information: file name, MDF version,
author, comment, recording start time, and recording duration
[REQ-MDF-050]. Any of these fields that are absent or unreadable in the
source file are exposed as empty/unknown rather than causing the file to
fail loading [REQ-MDF-051].

## Finding Channels by Name

The application can look up all channels across all groups that share an
exact given name, returning an empty result rather than an error when the
file has no such channel or no file is open [REQ-MDF-060]. This is the
mechanism other features use to re-locate a previously known signal by
name — e.g. carrying active signals over to a newly loaded file, or
resolving signals when restoring a saved session.

## Malformed / Partial Content Resilience

The application must never crash on malformed, incomplete, or unexpected
MDF content [REQ-MDF-070]. A channel that cannot be described during
discovery (e.g. corrupt channel metadata) is skipped rather than aborting
discovery of the rest of the file [REQ-MDF-071]. If the channel hierarchy
itself cannot be enumerated at all, that is reported as a load failure
rather than presenting a partial or incorrect tree silently [REQ-MDF-072].

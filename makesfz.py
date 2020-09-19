#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create SFZ file from a directory of samples."""

import argparse
import logging
import pathlib
import re
import sys
from collections import namedtuple
from itertools import groupby
from operator import attrgetter, itemgetter
from os.path import abspath, basename, exists, join as pathjoin, sep as pathsep, splitext

from jinja2 import Environment, FileSystemLoader, select_autoescape

import wavfile
from onsetdetect import get_offset
from pitchdetect import estimate_root_note


__program__ = "makesfz"
__version__ = "0.2.0"
log = logging.getLogger(__program__)

SFZ_TMPL = """\
<global>
loop_mode=no_loop

{% for root_note, region in regions -%}
{% for i, layer in enumerate(sorted(region.layers.values(), key=attrgetter('lovel'))) -%}
<group>
lokey={{ region.lokey }}
pitch_keycenter={{ region.root_note }}
hikey={{ region.hikey }}
{% if layer.lovel != 0 %}lovel={{ layer.lovel }}{% endif -%}
{% if layer.hivel != 127 %}hivel={{ layer.hivel }}{% endif %}
{# volume={{ (3-i) * -5}} -#}
{% if layer.hivel < 127 -%}
amp_velcurve_{{ layer.hivel }}=1
{% endif -%}
seq_length={{ layer.samples|length }}
{% for j, sample in enumerate(layer.samples.values()) -%}
<region>
seq_position={{ j+1 }}
sample={{ sample.path }}
{% if sample.tune %}tune={{ sample.tune }}{% endif -%}
{% if sample.offset %}offset={{ sample.offset }}{% endif %}
{% endfor %}
{% endfor %}
{% endfor %}
"""
FILE_TYPES = {
    "wav": ("wav",),
    "aif": ("aif", "aiff"),
    "flac": ("flac",),
}
RX_NOTE_INFO = (
    r"(?P<basenote>[abcdefgh])(?P<accidental>[#b]|es|is)?(-?(?P<octave>\d+))?"
    r"\s+(?P<layer>pp|p|mp|mf|f|ff)\s+(?P<sequence_no>\d)"
)
NOTES = ("c", "c#", "d", "d#", "e", "f", "f#", "g", "g#", "a", "a#", "b")
SAMPLE_LAYER_VELOCITIES = {
    "p": (0, 31),
    "mp": (32, 95),
    "f": (96, 127),
    "soft": (0, 63),
    "loud": (64, 127),
    "all": (0, 127),
}

Sample = namedtuple(
    "Sample", ["path", "root_note", "tune", "offset", "layer", "sequence_no"]
)
SampleLayer = namedtuple("SampleLayer", ["hivel", "lovel", "samples"])
SampleRegion = namedtuple("SampleRegion", ["root_note", "hikey", "lokey", "layers"])


def normalize_note(note):
    """Translate accidentals and normalize flats to sharps.

    For example E#->F, F##->G, Db->C#

    """
    index = NOTES.index(note[0].lower())

    for accidental in note[1:]:
        if accidental in ("#", "is"):
            index += 1
        elif accidental in ("b", "es"):
            index -= 1

    return NOTES[index % 12]


def note_name_to_number(note, base_octave=0):
    """Get MIDI note number from note name."""
    ocatve = 4
    note = note.strip().lower()

    if note[-1].isdigit():
        note, octave = note[:-1], int(note[-1])

    if len(note) > 1:
        note = normalize_note(note)

    return NOTES.index(note) + 12 * (octave - base_octave)


def get_root_note(
    path, sample_info, base_octave=0, ignore_metadata=False, detect_pitch=True
):
    root_note = None

    if not ignore_metadata and path.suffix.lower() == ".wav":
        try:
            wv = wavfile.WavFile(str(path))
        except wavfile.Error as exc:
            log.warning("Could not parse WAV file '%s': %s", path, exc)
        else:
            if wv.has_chunk("smpl") and wv.smpl.midi_unity_note:
                root_note = wv.smpl.midi_unity_note
                log.debug("Sample root note found in 'smpl' chunk: %i", root_note)

    if root_note is None:
        acc = sample_info["accidental"] or ""
        acc = {"es": "b", "is": "#"}.get(acc, acc)
        note = sample_info["basenote"].lower()

        if note == "h":
            note = "b"

        root_note = note_name_to_number(
            note + acc + (sample_info["octave"] or ""), base_octave
        )

    if root_note is None and detect_pitch:
        root_note = estimate_root_note(path, start=50)

    return root_note


def find_files(rootdir, extensions=None):
    dirpath = pathlib.Path(rootdir)

    if dirpath.is_dir():
        files = []

        for path in dirpath.iterdir():
            if path.is_file() and (
                extensions is None or splitext(path)[1] in extensions
            ):
                files.append(path)
            elif path.is_dir():
                files.extend(find_files(path, extensions))

        return files


def find_samples(rootdir, file_types):
    extensions = set()
    for ftype in file_types.split(","):
        ftype = ftype.strip().lower()
        extensions.update("." + ext for ext in FILE_TYPES.get(ftype, (ftype,)))

    return find_files(rootdir, extensions)


def strip_dirs(path, keep_dirs=1):  #
    pathcomps = abspath(path).split(pathsep)
    return pathjoin(*pathcomps[-(keep_dirs + 1) :])


def main(args=None):
    ap = argparse.ArgumentParser(prog=__program__, description=__doc__)
    # ap.set_defaults(**options)
    ap.add_argument(
        "-b",
        "--base-octave",
        type=int,
        metavar="NUM",
        default=-2,
        help="Number of base octave starting with MIDI note 0 (default: %(default)i).",
    )
    ap.add_argument(
        "-f",
        "--file-types",
        default="aif, flac, wav",
        metavar="TYPE",
        help="Comma-separated list of audio file types to include (default: %(default)s).",
    )
    ap.add_argument(
        "-r",
        "--regex",
        default=RX_NOTE_INFO,
        help="Regex for parsing sample root note, velocity and round-robin sequence from filename."
    )
    ap.add_argument(
        "-i",
        "--ignore-metadata",
        action="store_true",
        help="Ignore sample root note set in file meta data.",
    )
    ap.add_argument(
        "-o",
        "--detect-offset",
        action="store_true",
        help="Try to detect offset of sample onset through audio analysis.",
    )
    ap.add_argument(
        "-p",
        "--detect-pitch",
        action="store_true",
        help="Try to detect pitch of samples through audio analysis.",
    )
    ap.add_argument(
        "-H",
        "--high-key",
        metavar="KEY",
        help="Highest key to include in the highest sample region (NOT IMPLEMENTED).",
    )
    ap.add_argument(
        "-L",
        "--low-key",
        metavar="KEY",
        help="Lowest key to include in the lowest sample region (NOT IMPLEMENTED).",
    )
    ap.add_argument(
        "-k",
        "--keep-dirs",
        type=int,
        metavar="LEVEL",
        default=1,
        help="Number of directory levels to keep on sample file paths (default: %(default)i).",
    )
    ap.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Be more verbose"
    )
    ap.add_argument(
        "--version", action="version", version=__version__, help="Show version number"
    )
    ap.add_argument(
        "sampledir", help="The path of the directory containing the samples"
    )

    args = ap.parse_args(args=args)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s - %(message)s",
    )

    env = Environment(
        loader=FileSystemLoader("templates"), autoescape=select_autoescape(["tmpl"])
    )
    template = env.from_string(SFZ_TMPL)
    regex = re.compile(args.regex, re.IGNORECASE)

    samples = []

    if not exists(args.sampledir):
        return "Sample directory not found: %s" % args.sampledir

    for path in find_samples(args.sampledir, args.file_types):
        sample_path = strip_dirs(str(path), args.keep_dirs)
        match = regex.search(path.stem)
        if not match:
            log.warning(
                "Sample '{}' did not match regex. Skipping it.".format(path.stem)
            )
            continue

        info = match.groupdict()
        sequence_no = info.get("sequence_no")
        layer = info.get("layer") or "all"

        root = get_root_note(
            path, info, args.base_octave, args.ignore_metadata, args.detect_pitch
        )

        if root is None:
            root_note = 60
            tune = 0
        else:
            root_note = round(root)
            diff = root_note - root
            tune = round(diff * 100) if diff else None

        if args.detect_offset:
            offset = get_offset(str(path))[0]
        else:
            offset = 0

        samples.append(
            Sample(
                path=sample_path,
                root_note=root_note,
                tune=tune,
                offset=offset,
                layer=layer,
                sequence_no=sequence_no,
            )
        )

    regions = {}
    for sample in samples:
        if sample.root_note not in regions:
            regions[sample.root_note] = region = SampleRegion(
                sample.root_note, sample.root_note, sample.root_note, layers={}
            )
        else:
            region = regions[sample.root_note]

        if sample.layer not in region.layers:
            lovel, hivel = SAMPLE_LAYER_VELOCITIES[sample.layer]
            region.layers[sample.layer] = layer = SampleLayer(hivel, lovel, samples={})
        else:
            layer = region.layers[sample.layer]

        if sample.sequence_no is None:
            sample = sample._replace(sequence_no=len(layer.samples) + 1)

        if sample.sequence_no in layer.samples:
            log.warning(
                "Multiple samples for  sequence slot '{}'. Ignoring sample '{}'.".format(
                    sample.sequence_no, sample.path
                )
            )
            continue

        layer.samples[sample.sequence_no] = sample

    print(
        template.render(
            regions=sorted(regions.items()),
            enumerate=enumerate,
            attrgetter=attrgetter,
            sorted=sorted,
        )
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)

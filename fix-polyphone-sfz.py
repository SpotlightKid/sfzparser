#!/usr/bin/env python
"""Fix note related opcode values in an SFZ file exported by Polyphone."""

import argparse
import re
import sys
from os.path import exists


SFZ_NOTE_LETTER_OFFSET = {'a': 9, 'b': 11, 'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7}


def sfz_note_to_midi_key(sfz_note):
    accidental = 0

    if '#' in sfz_note or '♯' in sfz_note:
        accidental = 1
    elif 'b' in sfz_note or '♭' in sfz_note:
        accidental = -1

    letter = sfz_note[0].lower()
    octave = int(sfz_note[-1])
    return max(0, min(127, SFZ_NOTE_LETTER_OFFSET[letter] + ((octave + 1) * 12) + accidental))


def replace_key(match):
    opcode = match.group(1)
    note_name = match.group(2)

    if note_name is not None:
        return "%s=%s" % (opcode, sfz_note_to_midi_key(note_name))

    return match.group(0)


def main(args=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('-i', '--inplace', action="store_true",
                    help="Change input file in-place")
    ap.add_argument('sfzfile', help="SFZ input file")
    ap.add_argument('output', nargs="?", help="SFZ output file")

    args = ap.parse_args(args)

    if not exists(args.sfzfile):
        ap.print_help()
        return "\nErrorr: File not found: %s" % args.sfzfile

    if args.inplace and args.output:
        ap.print_help()
        return "\nError: Option -i/--inplace and output file argument are mutually exclusive"

    with open(args.sfzfile) as infp:
        sfz = infp.read()

    total_subs = 0
    for opcode in ('hikey', 'key', 'lokey', 'pitch_keycenter'):
        RX = re.compile(r"\b(%s)=([a-h](#|♯|b|♭)?\d+)" % opcode, re.IGNORECASE | re.UNICODE)
        sfz, num_subs = RX.subn(replace_key, sfz)
        total_subs += num_subs

        if num_subs:
            print("Fixed %d occurences of opcode '%s'" % (num_subs, opcode), file=sys.stderr)

    print("Total opcodes fixed: %d" % total_subs, file=sys.stderr)

    if args.inplace:
        outfp = open(args.sfzfile, 'w')
    elif args.output:
        outfp = open(args.output, 'w')
    else:
        outfp = sys.stdout

    with outfp:
        outfp.write(sfz)


if __name__ == '__main__':
    sys.exit(main() or 0)

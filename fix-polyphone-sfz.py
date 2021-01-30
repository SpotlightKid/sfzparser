#!/usr/bin/env python
"""Fix note related opcode values in an SFZ file exported by Polyphone."""

import argparse
import re
import sys
from os.path import exists


SFZ_NOTE_LETTER_OFFSET = {'a': 9, 'b': 11, 'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7}
NOTE_RX = re.compile(r"\b(hikey|key|lokey|pitch_keycenter)=([a-h](#|♯|b|♭)?\d+)\b",
                     re.IGNORECASE | re.UNICODE)



def sfz_note_to_midi_key(sfz_note, german=False):
    accidental = 0

    if '#' in sfz_note[1:] or '♯' in sfz_note:
        accidental = 1
    elif 'b' in sfz_note[1:] or '♭' in sfz_note:
        # Polyphone fortunately does not use flats, AFAICS,
        # that would create ambiguities when German note names are used.
        accidental = -1

    letter = sfz_note[0].lower()

    if german:
        if letter == 'b':
            accidental = -1
        if letter == 'h':
            letter = 'b'

    octave = int(sfz_note[-1])
    return max(0, min(127, SFZ_NOTE_LETTER_OFFSET[letter] + ((octave + 1) * 12) + accidental))


def replace_key(match, german=False):
    opcode = match.group(1)
    note_name = match.group(2)

    if note_name is not None:
        return "%s=%s" % (opcode, sfz_note_to_midi_key(note_name, german))

    return match.group(0)


def main(args=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('-g', '--german', action="store_true",
                    help="Input uses mixed/German note names")
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


    if re.search(r"\b(hikey|key|lokey|pitch_keycenter)=h\d+", sfz, re.I):
        print("Detected use of mixed/German note names. Enabling '-g' option.", file=sys.stderr)
        args.german = True

    sfz, num_subs = NOTE_RX.subn(lambda m: replace_key(m, args.german), sfz)

    print("Total opcodes fixed: %d" % num_subs, file=sys.stderr)

    if args.inplace:
        outfp = open(args.sfzfile, 'w')
    elif args.output:
        outfp = open(args.output, 'w')
    else:
        outfp = sys.stdout

    if num_subs or not args.inplace:
        with outfp:
            outfp.write(sfz)


if __name__ == '__main__':
    sys.exit(main() or 0)

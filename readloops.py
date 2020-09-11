#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import wavfile


for path in sys.argv[1:]:
    print("File:", os.path.basename(path))
    try:
        wav = wavfile.WavFile(path)
    except wavfile.Error as exc:
        print("Could not parse WAV file '{}': {}".format(path, exc), file=sys.stderr)
    else:
        if wav.smpl:
            print("Root note: {}".format(wav.smpl.midi_unity_note))
            for loop in wav.smpl.loops:
                print("Loop #{cue_point_id} - start: {start:10d} end: {end:10d}".format(**loop))

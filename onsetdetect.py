"""Detect onset of signal in audio files.

Requires:

* [aubio](https://pypi.org/project/aubio/)

"""

import sys
import logging

import aubio


__all__ = ("detect_onset", "get_offset")
log = logging.getLogger(__name__)


def detect_onsets(
    source,
    method="default",
    threshold=0.5,  # default ~0.058
    silence=-70.0,
    min_interval=0.05,
    buf_size=512,
    hop_size=256,
    samplerate=0,
    channels=0,
):
    """Detect pitches of given audio source.

    Supported methods: `energy`, `hfc`, `complex`, `phase`, `specdiff`, `kl`,
        `mkl`, `specflux`, `default`(`hfc`).

    """
    if not isinstance(source, aubio.source):
        source = aubio.source(
            source, hop_size=hop_size, samplerate=samplerate, channels=channels
        )

    with source:
        onsetdetect = aubio.onset(
            method=method,
            buf_size=buf_size,
            hop_size=hop_size,
            samplerate=source.samplerate,
        )
        onsetdetect.set_threshold(threshold)
        onsetdetect.set_silence(silence)
        onsetdetect.set_minioi_s(min_interval)

        results = []
        nframes = 0

        while True:
            block, read = source()

            if onsetdetect(block):
                results.append(onsetdetect.get_last())

            nframes += read
            if read < source.hop_size:
                break

    return results


def get_offset(fn, buf_size=512, hop_size=256, samplerate=0, channels=0):
    source = aubio.source(
        fn, hop_size=hop_size, samplerate=samplerate, channels=channels
    )
    onsets = detect_onsets(source)
    offset = 0

    if len(onsets) > 1 and onsets[0] == 0:
        offset = onsets[1]
    elif onsets:
        offset = onsets[0]

    if offset > source.samplerate / 2:
        log.warning("%s: detected sample onset offset > 0.5 s!. Assuming offset=0.", fn)
        offset = 0

    return offset, onsets


if __name__ == "__main__":
    from os.path import basename

    if len(sys.argv) < 2:
        sys.exit("usage: onsetdetect.py <wavfile>")
    else:
        infile = sys.argv[1]

    offset, onsets = get_offset(infile)
    print(
        "{}, offset={}, onsets: {}".format(
            basename(infile), offset, ",".join(str(o) for o in onsets)
        )
    )

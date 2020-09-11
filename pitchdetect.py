"""Detect pitch of audio files.

Requires:

* [aubio](https://pypi.org/project/aubio/)
* [NumPy](https://pypi.org/project/numpy/)

"""

import statistics

import aubio
import numpy as np


__all__ = ("detect_pitch", "estimate_root_note", "remove_outliers")


def remove_outliers(a, constant=1.5):
    """Remove outliers in given series using interquartile range (IQR)."""
    if not isinstance(a, np.ndarray):
        a = np.array(list(a))

    upper_quartile = np.percentile(a, 75)
    lower_quartile = np.percentile(a, 25)
    IQR = (upper_quartile - lower_quartile) * constant
    quartile_set = (lower_quartile - IQR, upper_quartile + IQR)
    return [y for y in a.tolist() if y >= quartile_set[0] and y <= quartile_set[1]]


def detect_pitch(
    source,
    method="default",
    tolerance=0.8,  # got value from aubio Python demos
    silence=-70.0,
    unit="Hz",
    buf_size=1024,
    hop_size=256,
    samplerate=0,
    channels=0,
):
    """Detect pitches of given audio source.

    Supported methods: `yinfft`, `yin`, `yinfast`, `fcomb`, `mcomb`,
    `schmitt`, `specacf`, `default` (`yinfft`).

    """
    if not isinstance(source, aubio.source):
        source = aubio.source(
            source, hop_size=hop_size, samplerate=samplerate, channels=channels
        )

    with source:
        pitchdetect = aubio.pitch(
            method=method,
            buf_size=buf_size,
            hop_size=hop_size,
            samplerate=source.samplerate,
        )
        pitchdetect.set_tolerance(tolerance)
        pitchdetect.set_silence(silence)
        pitchdetect.set_unit(unit)

        results = []
        nframes = 0

        while True:
            block, read = source()
            confidence = pitchdetect.get_confidence()

            results.append((nframes, pitchdetect(block)[0], confidence))

            nframes += read
            if read < source.hop_size:
                break

    return results


def estimate_root_note(fn, start=0, end=None):
    """Estimate root MIDI note of given sample using harmonic mean of detected pitches.

    Detectd pitches of zero and outliers of detected pitches are removed using interquartile range.

    """
    data = detect_pitch(fn, unit="midi")
    if start or end:
        if end is None:
            end = len(data)
        data = data[start:end]

    return statistics.harmonic_mean(
        remove_outliers([i[1] for i in data if i[0] != 0.0])
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        sys.exit("usage: pitchdetect.py <wavfile>")

    data = detect_pitch(sys.argv[1])
    cleaned = remove_outliers([i[1] for i in data])

    print("Simple mean: {:.4f} Hz".format(statistics.mean(cleaned)))
    print("Geometric mean: {:.4f} Hz".format(statistics.geometric_mean(cleaned)))
    print("Harmonic mean: {:.4f} Hz".format(statistics.harmonic_mean(cleaned)))
    print("Median: {:.4f} Hz".format(statistics.median(cleaned)))
    print("Standard dev.: {:.6f}\n".format(statistics.stdev(cleaned)))
    print("MIDI note: {}".format(estimate_root_note(sys.argv[1])))

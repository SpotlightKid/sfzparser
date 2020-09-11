# -*- coding: utf-8 -*-

__all_ = [
    'Error',
    'FmtChunk',
    'ParsingError',
    'SmplChunk',
    'UnsupportedCompressionError',
    'WavChunk',
    'WavFile'
]

import logging
import struct

from chunk import Chunk


if not isinstance('', bytes):
    basestring = str


# module globals
log = logging.getLogger(__name__)

KNOWN_CHUNKS = [
    b'cue ',
    b'data',
    b'fact',
    b'fmt ',
    b'inst',
    b'list',
    b'plst',
    b'smpl',
    b'wavl',
]
# sub-chunks of 'list'
#    'ltxt',
#    'note',
#    'labl',

FORMAT_TAGS = {
    0: 'Unknown',
    1: 'PCM/uncompressed',
    2: 'Microsoft ADPCM',
    6: 'ITU G.711 a-law',
    7: 'ITU G.711 u-law',
    17: 'IMA ADPCM',
    20: 'ITU G.723 ADPCM',
    49: 'GSM 6.10',
    64: 'ITU G.721 ADPCM',
    80: 'MPEG',
    0xFFFF: 'Experimental',
}

LOOP_TYPE_FORWARD = 0
LOOP_TYPE_ALTERNATE = 1
LOOP_TYPE_REVERSE = 2
WAVE_FORMAT_PCM = 0x0001


# exceptions
class Error(Exception):
    """General error."""
    pass


class ParseError(Error):
    pass


class UnsupportedFileTypeError(Error):
    pass


class UnsupportedCompressionError(Error):
    pass


# utility functions
def _unpack_to_dict(format, data, offset=0, *names):
    return dict(zip(names, struct.unpack_from(format, data, offset)))


def chunk_factory(file):
    fourcc = file.read(4)

    if len(fourcc) < 4:
        raise EOFError("Stream too short for RIFF type file.")

    return _chunk_registry.get(fourcc, _chunk_registry[None])(file, name=fourcc)


# API classes
class WavChunk(Chunk):
    """Base class for chunks in a WAVE RIFF file.

    Sub-classes chunk.Chunk but offers more convenient property-based access
    to chunk data. Attributes:

        - name: four-character chunk tag name
        - size: length of chunk data
        - data: raw chunk data

    Specialized sub-classes for specific chunk types may add more attributes
    for parsed chunk data.

    Getting the string value of an instance (e.g. via 'str()' or 'print'),
    yields the binary chunk data including tag and size fields and appopriate
    data padding.

    """
    fourcc = b''
    _fieldnames = ()
    _pack_format = ''

    def __init__(self, file, name=None):
        self.closed = False
        # whether to align to word (2-byte) boundaries
        self.align = True
        self.file = file

        if name is None:
            self.chunkname = file.read(4)
            if len(self.chunkname) < 4:
                raise EOFError
        else:
            self.name = name

        try:
            self.chunksize = struct.unpack('<L', file.read(4))[0]
        except struct.error:
            raise EOFError

        self.size_read = 0

        try:
            self.offset = self.file.tell()
        except (AttributeError, IOError):
            self.seekable = False
            self._data = self.read()
        else:
            self.seekable = True
            self._data = None

    def _get_name(self):
        return self.chunkname
    def _set_name(self, name):
        if len(name) > 4:
            raise ValueError("Chunk tag name length must be 4 characters.")

        self.chunkname = name + b' ' * max(0, 4 - len(name))
    name = property(_get_name, _set_name, None, "Four-character chunk tag.")

    @property
    def size(self):
        if self._data is None:
            return self.chunksize
        else:
            return len(self.data)

    @property
    def data(self):
        if self._data is None:
            log.debug("Reading data from %s", self.__class__.__name__)
            self.seek(0)
            self._data = self.read()

        return self._data

    def __repr__(self):
        return (" ".join(["%02X" % c if isinstance(c, int) else ord(c)
            for c in self.data[:100]]) +
            (" [...]" if len(self.data) > 100 else ""))

    def __str__(self):
        fmt = '<4sL%is' % len(self.data)
        packed_size = struct.pack('<L', len(self.data))
        log.debug("Data size: %i (%r)", len(self.data), packed_size)
        return struct.pack(fmt, self.name, len(self.data), self.data) + (
            '\0' if len(self.data) % 2 else '')

    def __getattr__(self, name):
        log.debug("%s.__getattr__(%r) called.", self.__class__.__name__, name)
        # attribute access triggers deferred parsing of chunk data
        if self._data is None:
            self._parse()

        try:
            return self.__dict__[name]
        except KeyError:
            raise AttributeError(name)

    def _parse(self):
        log.debug("%s._parse() called.", self.__class__.__name__)
        try:
            self.__dict__.update(_unpack_to_dict(self._pack_format, self.data,
                0, *self._fieldnames))
        except struct.error:
            raise ParseError("Invalid data in '%s' chunk." % self.fourcc)


class FmtChunk(WavChunk):

    fourcc = 'fmt '
    _pack_format = '<hhllh'
    _fieldnames = (
        'format_tag',
        'channels',
        'samples_per_sec',
        'avg_bytes_per_sec',
        'block_align')

    def _parse(self):
        WavChunk._parse(self)

        if self.format_tag == WAVE_FORMAT_PCM:
            self.bits_per_sample = struct.unpack('<h', self.data[14:16])[0]
            self.compressed = False
        else:
            self.compressed = True

            if self.format_tag not in FORMAT_TAGS:
                log.warn('Unknown format tag: %r', self.format_tag)

    @property
    def comp_name(self):
        return FORMAT_TAGS.get(self.format_tag, '<unsupported>')

    @property
    def sample_width(self):
        if self.format_tag == WAVE_FORMAT_PCM:
            return (self.bits_per_sample + 7) // 8
        else:
            raise UnsupportedCompressionError("Can't determine sample width "
                "for %s data compression format.", self.comp_name)

    @property
    def frame_size(self):
        return self.channels * self.sample_width


class SmplChunk(WavChunk):
    """Represents a 'smpl' chunk with information for samplers."""

    fourcc = 'smpl'
    _pack_format = '<9l'
    _loop_pack_format = '<6l'
    _fieldnames = (
        'manufacturer',
        'product',
        'sample_period',
        'midi_unity_note',
        'midi_pitch_fraction',
        'smpte_format',
        'smpte_offset',
        'sample_loops',
        'sampler_data')
    _loop_fieldnames = (
        'cue_point_id',
        'type',
        'start',
        'end',
        'fraction',
        'play_count')

    def _parse(self):
        WavChunk._parse(self)
        self.loops = []

        for i in range(self.sample_loops):
            self.loops.append(
                _unpack_to_dict(self._loop_pack_format, self.data,
                struct.calcsize(self._pack_format), *self._loop_fieldnames))


class ListChunk(WavChunk):
    """Represents a 'list' chunk, which has a type and contains sub-chunks.

    The list type is available through the 'type_id' attribute, the list of
    sub-chunks through the 'subchunks' attribute. Each list item is a tuple
    with the four-character chunk tag as the first item and the raw chunk data
    (as a byte string) as the second.

    """
    _fieldnames = ('type_id',)
    _pack_format = '<4s'

    def _parse(self):
        WavChunk._parse(self)
        pos = 4
        self.subchunks = []

        while pos < len(self.data):
            tag = self.data[pos:pos+4]
            size = struct.unpack_from('<l', self.data, pos + 4)[0]
            self.subchunks.append((tag, self.data[pos+8:pos+8+size]))
            pos += 8 + size + (1 if size % 2 else 0)


class CueChunk(WavChunk):
    """Represents a 'cue ' chunk with the list of cue points."""

    fourcc = 'cue '
    _pack_format = '<l'
    _cue_pack_format = '<2l4s3l'
    _fieldnames = ('num_cue_points')
    _loop_fieldnames = (
        'id',
        'position',
        'data_chunk_id',
        'chunk_start',
        'block_start',
        'sample_offset')

    def _parse(self):
        WavChunk._parse(self)
        self.cue_points = []

        for i in range(self.num_cue_points):
            self.cue_points.append(
                _unpack_to_dict(self._cue_pack_format, self.data,
                struct.calcsize(self._pack_format), *self._cue_fieldnames))


class WavFile(object):
    """WAV file reader."""

    def __init__(self, wavfile):
        self._i_opened_the_file = False

        if isinstance(wavfile, str):
            self.filename = wavfile
            self.file = open(self.filename, 'rb')
            self._i_opened_the_file = True
        else:
            self.file = wavfile
            try:
                self.filename = wavfile.name
            except AttributeError:
                self.filename = None

        try:
            self._riff = Chunk(self.file, align=True, bigendian=False)

            riff_name = self._riff.getname()
            if riff_name != b'RIFF':
                raise ValueError("First chunk name != 'RIFF' (value '%s')" %
                    riff_name)
        except (EOFError, ValueError):
            raise ParseError("%s: Invalid/missing RIFF tag or chunk size." %
                self.filename)

        if self._riff.read(4) != b'WAVE':
            raise Error("%s: not a WAVE file" % self.filename)

        # dict to store chunk by chunk name (four-cc tag)
        self.chunks = dict()
        # we keep an extra list of chunks to maintain chunk position
        self._chunklist = []

        while True:
            try:
                chunk = chunk_factory(self._riff)
            except EOFError:
                break

            if chunk.name == b'data' and b'fmt ' not in self.chunks:
                log.warn("Encountered 'data' chunk before 'fmt ' chunk.")

            if chunk.name in KNOWN_CHUNKS:
                if chunk.name in self.chunks:
                    log.warn("Ignoring extra '%s' chunk at %i bytes."
                        % (chunk.name, self._riff.tell()))
                else:
                    self.chunks[chunk.name] = chunk
            else:
                self.chunks.setdefault(chunk.name, []).append(chunk)

            self._chunklist.append(chunk)
            chunk.skip()

        if b'fmt ' not in self.chunks or b'data' not in self.chunks:
            raise ParseError("'fmt ' chunk and/or 'data' chunk missing.")

    def close(self):
        if self._i_opened_the_file:
            try:
                self.file.close()
            except:
                pass

    __del__ = close

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def __repr__(self):
        s = []
        for chunk in self:
            s.append("Chunk '%s': size %i (%r)\n" % (
                chunk.name.decode('ascii'), chunk.size, chunk))
        return "".join(s)

    def __str__(self):
        data = b"".join(str(chunk) for chunk in self)
        packed_size = struct.pack('<l', len(data) + 4)
        log.debug("Data size: %i (%r)", len(data), packed_size)
        return b"RIFF" + packed_size + b"WAVE" + data

    def __iter__(self):
        """Make object useable as an iterator which yields each RIFF chunk.

        The original position of each chunk in the source file is kept except
        for the 'fmt ' chunk, which is always returned first.

        """
        yield self.chunks[b'fmt ']
        for chunk in self.chunks.get(b'LIST', []):
            if chunk.type_id == b'INFO':
                yield chunk
        for chunk in self._chunklist:
            if chunk.name == b'fmt ':
                continue
            if chunk.name == b'LIST' and chunk.type_id == b'INFO':
                continue

            yield chunk

    def has_chunk(self, chunk_id):
        if isinstance(chunk_id, str):
            chunk_id = chunk_id.encode()
        return chunk_id in self.chunks

    @property
    def fmt(self):
        try:
            return self.chunks[b'fmt ']
        except KeyError:
            log.warning("'fmt ' chunk not found.")
            return None

    @property
    def smpl(self):
        try:
            return self.chunks[b'smpl']
        except KeyError:
            log.warning("'smpl' chunk not found.")
            return None

    @property
    def loops(self):
        try:
            return self.chunks[b'smpl'].loops
        except KeyError:
            return []

    @property
    def cue_points(self):
        try:
            return self.chunks[b'cue '].loops
        except KeyError:
            return []

    @property
    def info(self):
        try:
            for chunk in self.chunks.get(b'LIST', []):
                if chunk.type_id == b'INFO':
                    return dict((key, val.rstrip('\0'))
                        for key, val in chunk.subchunks)
        except KeyError:
            pass
        return dict()

    def raw_frames(self):
        data = self.chunks[b'data'].data
        size = len(data)
        fs = self.fmt.frame_size
        pos = 0

        while pos <= size - fs:
            yield data[pos:pos+fs]
            pos += fs


_chunk_registry = {
    b'cue ': CueChunk,
    b'fmt ': FmtChunk,
    b'smpl': SmplChunk,
    b'list': ListChunk,
    b'LIST': ListChunk,
    None: WavChunk
}


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.DEBUG)

    try:
        if len(sys.argv) >= 2:
            wav = WavFile(sys.argv[1])
        else:
            wav = WavFile(sys.stdin)
    except Exception as exc:
        # XXX: for debugging, remove in release code
        import traceback
        traceback.print_exc()
        sys.exit(1)

    sys.stdout.write(repr(wav))
    print()

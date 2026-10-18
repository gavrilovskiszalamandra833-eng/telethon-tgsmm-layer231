try:
    from isal import igzip as gzip
except ImportError:
    import gzip
import struct

from .. import TLObject


class GzipPackedError(ValueError):
    """A malformed gzip error containing no compressed wire bytes."""

    def __init__(self, compressed_length, decompressor_error):
        super().__init__(
            'Could not decompress gzip-packed data (length {} bytes, error {})'
            .format(compressed_length, decompressor_error))
        self.compressed_length = compressed_length
        self.decompressor_error = decompressor_error


def _decompress(data):
    try:
        return gzip.decompress(data)
    except Exception as error:
        # gzip.BadGzipFile embeds input bytes in its message. Keep only the
        # exception class, then raise outside the handler so no unsafe error is
        # retained through __context__ or rendered as chained traceback text.
        error_type = type(error).__name__

    raise GzipPackedError(len(data), error_type)


class GzipPacked(TLObject):
    CONSTRUCTOR_ID = 0x3072cfa1

    def __init__(self, data):
        self.data = data

    @staticmethod
    def gzip_if_smaller(content_related, data):
        """Calls bytes(request), and based on a certain threshold,
           optionally gzips the resulting data. If the gzipped data is
           smaller than the original byte array, this is returned instead.

           Note that this only applies to content related requests.
        """
        if content_related and len(data) > 512:
            gzipped = bytes(GzipPacked(data))
            return gzipped if len(gzipped) < len(data) else data
        else:
            return data

    def __bytes__(self):
        return struct.pack('<I', GzipPacked.CONSTRUCTOR_ID) + \
               TLObject.serialize_bytes(gzip.compress(self.data))

    @staticmethod
    def read(reader):
        constructor = reader.read_int(signed=False)
        assert constructor == GzipPacked.CONSTRUCTOR_ID
        return _decompress(reader.tgread_bytes())

    @classmethod
    def from_reader(cls, reader):
        return GzipPacked(_decompress(reader.tgread_bytes()))

    def to_dict(self):
        return {
            '_': 'GzipPacked',
            'data': self.data
        }

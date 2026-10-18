"""
This module contains the BinaryReader utility class.
"""
import struct
import time
from datetime import datetime, timedelta, timezone

from ..errors import TypeNotFoundError
from ..tl.alltlobjects import tlobjects
from ..tl.core import core_objects

_EPOCH_NAIVE = datetime(*time.gmtime(0)[:6])
_EPOCH = _EPOCH_NAIVE.replace(tzinfo=timezone.utc)


# Keep the named compatibility surface while raising the exact builtin type.
# Some callers compare ``type(error) is BufferError`` rather than using
# ``isinstance``, and the layer-231 release audit preserves that behaviour.
BinaryReaderBufferError = BufferError


def _buffer_error(value_type, expected_length, available_length,
                  constructor_id=None):
    """Build a truncated-read error containing metadata, never wire bytes."""
    message = (
        'Not enough data to read {} (expected {} bytes, available {} bytes)'
        .format(value_type, expected_length, available_length))
    if constructor_id is not None:
        message += ' while decoding constructor {:08x}'.format(constructor_id)

    error = BinaryReaderBufferError(message)
    error.value_type = value_type
    error.expected_length = expected_length
    error.available_length = available_length
    error.constructor_id = constructor_id
    return error


class BinaryReader:
    """
    Small utility class to read binary data.
    """

    def __init__(self, data):
        self.stream = data or b''
        self.position = 0
        # Retain only metadata about reads. Keeping the bytes here makes them
        # reachable from exceptions and diagnostic tooling that captures locals.
        self._last = None
        self._constructor_ids = []

    # region Reading

    # "All numbers are written as little endian."
    # https://core.telegram.org/mtproto
    def read_byte(self):
        """Reads a single byte value."""
        return self._read_struct('<B', 'byte')

    def read_int(self, signed=True):
        """Reads an integer (4 bytes) value."""
        fmt = '<i' if signed else '<I'
        return self._read_struct(fmt, 'int')

    def read_long(self, signed=True):
        """Reads a long integer (8 bytes) value."""
        fmt = '<q' if signed else '<Q'
        return self._read_struct(fmt, 'long')

    def read_float(self):
        """Reads a real floating point (4 bytes) value."""
        return self._read_struct('<f', 'float')

    def read_double(self):
        """Reads a real floating point (8 bytes) value."""
        return self._read_struct('<d', 'double')

    def read_large_int(self, bits, signed=True):
        """Reads a n-bits long integer value."""
        return int.from_bytes(
            self.read(bits // 8, _value_type='large int'),
            byteorder='little', signed=signed)

    def _read_struct(self, fmt, value_type):
        length = struct.calcsize(fmt)
        value, = struct.unpack(fmt, self.read(length, _value_type=value_type))
        return value

    def read(self, length=-1, _value_type='bytes'):
        """Read the given amount of bytes, or -1 to read all remaining."""
        if length >= 0:
            result = self.stream[self.position:self.position + length]
            self.position += length
        else:
            result = self.stream[self.position:]
            self.position += len(result)
        if (length >= 0) and (len(result) != length):
            raise _buffer_error(
                _value_type,
                length,
                len(result),
                self._constructor_ids[-1] if self._constructor_ids else None)

        self._last = len(result)
        return result

    def get_bytes(self):
        """Gets the byte array representing the current buffer as a whole."""
        return self.stream

    # endregion

    # region Telegram custom reading

    def tgread_bytes(self):
        """
        Reads a Telegram-encoded byte array, without the need of
        specifying its length.
        """
        first_byte = self.read_byte()
        if first_byte == 254:
            length = self.read_byte() | (self.read_byte() << 8) | (
                self.read_byte() << 16)
            padding = length % 4
        else:
            length = first_byte
            padding = (length + 1) % 4

        data = self.read(length)
        if padding > 0:
            padding = 4 - padding
            self.read(padding)

        return data

    def tgread_string(self):
        """Reads a Telegram-encoded string."""
        return str(self.tgread_bytes(), encoding='utf-8', errors='replace')

    def tgread_bool(self):
        """Reads a Telegram boolean value."""
        value = self.read_int(signed=False)
        if value == 0x997275b5:  # boolTrue
            return True
        elif value == 0xbc799737:  # boolFalse
            return False
        else:
            raise RuntimeError('Invalid boolean code {}'.format(hex(value)))

    def tgread_date(self):
        """Reads and converts Unix time (used by Telegram)
           into a Python datetime object.
        """
        value = self.read_int()
        return _EPOCH + timedelta(seconds=value)

    def tgread_object(self):
        """Reads a Telegram object."""
        constructor_id = self.read_int(signed=False)
        clazz = tlobjects.get(constructor_id, None)
        if clazz is None:
            # The class was None, but there's still a
            # chance of it being a manually parsed value like bool!
            value = constructor_id
            if value == 0x997275b5:  # boolTrue
                return True
            elif value == 0xbc799737:  # boolFalse
                return False
            elif value == 0x1cb5c415:  # Vector
                return self._tgread_vector_body(constructor_id)

            clazz = core_objects.get(constructor_id, None)
            if clazz is None:
                # If there was still no luck, give up
                self.seek(-4)  # Go back
                pos = self.tell_position()
                raise TypeNotFoundError(
                    constructor_id, len(self.stream) - pos)

        self._constructor_ids.append(constructor_id)
        try:
            return clazz.from_reader(self)
        finally:
            self._constructor_ids.pop()

    def tgread_vector(self):
        """Reads a vector (a list) of Telegram objects."""
        constructor_id = self.read_int(signed=False)
        if 0x1cb5c415 != constructor_id:
            raise RuntimeError('Invalid constructor code, vector was expected')

        return self._tgread_vector_body(constructor_id)

    def _tgread_vector_body(self, constructor_id):
        self._constructor_ids.append(constructor_id)
        try:
            count = self.read_int()
            return [self.tgread_object() for _ in range(count)]
        finally:
            self._constructor_ids.pop()

    # endregion

    def close(self):
        """Closes the reader, freeing the BytesIO stream."""
        self.stream = b''

    # region Position related

    def tell_position(self):
        """Tells the current position on the stream."""
        return self.position

    def set_position(self, position):
        """Sets the current position on the stream."""
        self.position = position

    def seek(self, offset):
        """
        Seeks the stream position given an offset from the current position.
        The offset may be negative.
        """
        self.position += offset

    # endregion

    # region with block

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # endregion

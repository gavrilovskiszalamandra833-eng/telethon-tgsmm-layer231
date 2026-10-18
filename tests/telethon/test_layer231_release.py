import asyncio
import json
import logging
import struct
import traceback
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from telethon.errors import InvalidBufferError, TypeNotFoundError
from telethon.extensions import BinaryReader
from telethon.extensions.binaryreader import BinaryReaderBufferError
from telethon.network.mtprotosender import MTProtoSender, _log_type_not_found
from telethon.tl import TLObject, types
from telethon.tl.core import GzipPacked, RpcResult
from telethon.tl.core.gzippacked import GzipPackedError
from telethon.version import __version__


ROOT = Path(__file__).resolve().parents[2]


def test_release_uses_canonical_distribution_identity():
    pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    setup_py = (ROOT / 'setup.py').read_text(encoding='utf-8')
    manifest = json.loads(
        (ROOT / 'generated-layer231-manifest.json').read_text(encoding='utf-8'))

    assert 'name = "Telethon"' in pyproject
    assert "name='Telethon'" in setup_py
    assert 'Telethon-TGSMM-Layer231' not in pyproject
    assert 'Telethon-TGSMM-Layer231' not in setup_py
    assert __version__ == '1.45.0+tgsmm.layer231.2'
    assert manifest['release'] == {
        'distribution': 'Telethon',
        'version': __version__,
    }


def _roundtrip(value):
    payload = bytes(value)
    with BinaryReader(payload) as reader:
        result = reader.tgread_object()
        assert reader.tell_position() == len(payload)
    return result


def test_layer231_constructor_fixtures_roundtrip():
    transfer = types.MessageActionGramTransfer(
        amount=123456789,
        peer_address='UQ-peer',
        transaction_id='tx-231',
        comment='fixture',
    )
    service = types.MessageService(
        id=42,
        peer_id=types.PeerUser(1001),
        date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        action=transfer,
    )
    decoded_service = _roundtrip(service)
    assert isinstance(decoded_service, types.MessageService)
    assert isinstance(decoded_service.action, types.MessageActionGramTransfer)
    assert decoded_service.action.amount == 123456789
    assert decoded_service.action.peer_address == 'UQ-peer'
    assert decoded_service.action.transaction_id == 'tx-231'
    assert decoded_service.action.comment == 'fixture'

    wallet_update = _roundtrip(
        types.UpdateWalletState(types.WalletStateEmpty(creating=True)))
    assert isinstance(wallet_update, types.UpdateWalletState)
    assert wallet_update.state.creating is True

    user_full = _roundtrip(types.UserFull(
        id=1001,
        settings=types.PeerSettings(),
        notify_settings=types.PeerNotifySettings(),
        common_chats_count=0,
        gram_address='UQ-gram-address',
    ))
    assert user_full.gram_address == 'UQ-gram-address'

    verification = _roundtrip(types.BotVerification(
        bot_id=2002,
        icon=3003,
        description=types.TextWithEntities('verified', []),
    ))
    assert isinstance(verification.description, types.TextWithEntities)
    assert verification.description.text == 'verified'


@pytest.mark.parametrize(('name', 'constructor_id'), [
    ('MessageActionGramTransfer', 0x9329EA33),
    ('UpdateWalletState', 0x6AC3F2AA),
    ('UserFull', 0x7FE738C4),
    ('BotVerification', 0xF72E0ED9),
])
def test_layer231_constructor_ids(name, constructor_id):
    assert getattr(types, name).CONSTRUCTOR_ID == constructor_id


def test_unknown_constructor_error_never_retains_or_formats_payload():
    secret = b'never-log-this-payload'
    constructor_id = 0xDEADBEEF
    payload = struct.pack('<I', constructor_id) + secret

    with pytest.raises(TypeNotFoundError) as raised:
        BinaryReader(payload).tgread_object()

    error = raised.value
    assert error.invalid_constructor_id == constructor_id
    assert error.remaining_length == len(payload)
    assert secret.decode() not in str(error)
    assert repr(secret) not in str(error)
    assert not isinstance(getattr(error, 'remaining', None), bytes)


def test_unknown_constructor_log_has_only_id_and_length(caplog):
    secret = b'unknown-secret-payload'
    constructor_id = 0xDEADBEEF
    payload = struct.pack('<I', constructor_id) + secret
    sender = object.__new__(MTProtoSender)
    sender._log = logging.getLogger('telethon.layer231.unknown')

    caplog.set_level(logging.INFO, logger=sender._log.name)
    with pytest.raises(TypeNotFoundError) as raised:
        BinaryReader(payload).tgread_object()
    error = raised.value
    _log_type_not_found(sender._log, error)

    assert caplog.messages == [
        'Type deadbeef not found, remaining data length {}'.format(len(payload))]
    assert secret.decode() not in caplog.text
    assert repr(secret) not in caplog.text


def test_orphan_response_log_has_only_constructor_id_and_length(caplog):
    secret = b'orphan-secret-payload'
    constructor_id = 0xDEADBEEF
    body = struct.pack('<I', constructor_id) + secret
    sender = object.__new__(MTProtoSender)
    sender._pending_state = {}
    sender._log = logging.getLogger('telethon.layer231.orphan')
    message = SimpleNamespace(obj=RpcResult(123, body, None))

    caplog.set_level(logging.INFO, logger=sender._log.name)
    asyncio.run(sender._handle_rpc_result(message))

    assert caplog.messages == [
        'Received response without parent request: constructor deadbeef, length {}'.format(
            len(body))]
    assert secret.decode() not in caplog.text
    assert repr(secret) not in caplog.text


def test_orphan_error_log_has_only_constructor_id_and_length(caplog):
    secret = 'orphan-error-secret'
    error = types.RpcError(error_code=-500, error_message=secret)
    sender = object.__new__(MTProtoSender)
    sender._pending_state = {}
    sender._log = logging.getLogger('telethon.layer231.orphan-error')
    message = SimpleNamespace(obj=RpcResult(123, None, error))

    caplog.set_level(logging.INFO, logger=sender._log.name)
    asyncio.run(sender._handle_rpc_result(message))

    assert caplog.messages == [
        'Received error without parent request: constructor {}, length {}'.format(
            format(error.CONSTRUCTOR_ID, '08x'), len(bytes(error)))]
    assert secret not in caplog.text


def _assert_payload_is_absent(text, secret):
    fragments = {secret, secret[:8], secret[-8:]}
    for fragment in fragments:
        if fragment:
            assert fragment.decode() not in text
            assert repr(fragment) not in text


def test_binary_reader_truncation_reports_only_safe_metadata():
    secret = b'binary-reader-secret'
    reader = BinaryReader(secret)

    with pytest.raises(BufferError) as raised:
        reader.read(len(secret) + 7)

    error = raised.value
    assert error.value_type == 'bytes'
    assert error.expected_length == len(secret) + 7
    assert error.available_length == len(secret)
    assert error.constructor_id is None
    _assert_payload_is_absent(str(error), secret)
    _assert_payload_is_absent(repr(error), secret)
    _assert_payload_is_absent(
        ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
        secret)


def test_binary_reader_buffer_error_keeps_builtin_compatibility():
    assert issubclass(BinaryReaderBufferError, BufferError)

    with pytest.raises(BufferError) as raised:
        BinaryReader(b'x').read(2)

    # The release audit and existing callers expect the builtin error type.
    assert type(raised.value) is BufferError


def test_binary_reader_truncation_does_not_format_previous_read():
    secret = b'previous-read-secret'
    reader = BinaryReader(secret)
    assert reader.read(len(secret)) == secret

    with pytest.raises(BufferError) as raised:
        reader.read(1)

    _assert_payload_is_absent(str(raised.value), secret)
    assert reader._last == len(secret)


def test_binary_reader_typed_truncation_includes_constructor_metadata():
    secret = b'typed-secret'
    constructor_id = types.PeerUser.CONSTRUCTOR_ID
    payload = struct.pack('<I', constructor_id) + secret[:3]

    with pytest.raises(BufferError) as raised:
        BinaryReader(payload).tgread_object()

    error = raised.value
    assert error.value_type == 'long'
    assert error.expected_length == 8
    assert error.available_length == 3
    assert error.constructor_id == constructor_id
    assert format(constructor_id, '08x') in str(error)
    _assert_payload_is_absent(str(error), secret[:3])


def test_binary_reader_vector_truncation_includes_vector_constructor_only():
    secret = b'vector-payload-sentinel'
    constructor_id = 0x1cb5c415
    payload = struct.pack('<I', constructor_id) + secret[:3]

    with pytest.raises(BufferError) as raised:
        BinaryReader(payload).tgread_object()

    error = raised.value
    assert error.value_type == 'int'
    assert error.expected_length == 4
    assert error.available_length == 3
    assert error.constructor_id == constructor_id
    assert format(constructor_id, '08x') in str(error)
    _assert_payload_is_absent(str(error), secret[:3])


@pytest.mark.parametrize(('method', 'value_type', 'expected_length'), [
    ('read_byte', 'byte', 1),
    ('read_int', 'int', 4),
    ('read_long', 'long', 8),
    ('read_float', 'float', 4),
    ('read_double', 'double', 8),
])
def test_binary_reader_fixed_width_truncation_is_sanitized(
        method, value_type, expected_length):
    secret = b'X' * (expected_length - 1)

    with pytest.raises(BufferError) as raised:
        getattr(BinaryReader(secret), method)()

    error = raised.value
    assert error.value_type == value_type
    assert error.expected_length == expected_length
    assert error.available_length == len(secret)
    _assert_payload_is_absent(str(error), secret)


def test_binary_reader_large_int_truncation_is_sanitized():
    secret = b'large-int-secret'

    with pytest.raises(BufferError) as raised:
        BinaryReader(secret).read_large_int(256)

    error = raised.value
    assert error.value_type == 'large int'
    assert error.expected_length == 32
    assert error.available_length == len(secret)
    _assert_payload_is_absent(str(error), secret)


def test_invalid_buffer_error_never_retains_or_formats_payload():
    secret = b'invalid-buffer-secret'
    error = InvalidBufferError(secret)

    assert error.value_type == 'response buffer'
    assert error.available_length == len(secret)
    assert error.expected_length == 8
    assert error.constructor_id is None
    assert not isinstance(getattr(error, 'payload', None), bytes)
    _assert_payload_is_absent(str(error), secret)
    _assert_payload_is_absent(repr(error), secret)


def test_sender_exception_and_sentry_style_log_do_not_expose_payload(caplog):
    secret = b'sender-decrypted-secret'
    logger = logging.getLogger('telethon.layer231.sender-truncation')

    class TruncatedRequest:
        @staticmethod
        def read_result(reader):
            return reader.read(len(secret) + 9)

    async def run():
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        state = SimpleNamespace(request=TruncatedRequest(), future=future)
        sender = object.__new__(MTProtoSender)
        sender._pending_state = {123: state}
        sender._log = logger
        message = SimpleNamespace(obj=RpcResult(123, secret, None))
        await sender._handle_rpc_result(message)
        error = future.exception()
        logger.error(
            'Sentry-style captured sender failure',
            exc_info=(type(error), error, error.__traceback__))
        return error

    caplog.set_level(logging.ERROR, logger=logger.name)
    error = asyncio.run(run())

    assert error.available_length == len(secret)
    _assert_payload_is_absent(str(error), secret)
    _assert_payload_is_absent(repr(error), secret)
    _assert_payload_is_absent(caplog.text, secret)


def test_sender_receive_log_does_not_expose_decrypted_payload(caplog):
    secret = b'recv-loop-sentinel-91af37cd'
    logger = logging.getLogger('telethon.layer231.safe-receive-path')
    reconnect_errors = []

    class Connection:
        @staticmethod
        async def recv():
            return secret

    class State:
        @staticmethod
        def decrypt_message_data(body):
            return BinaryReader(body).read(len(body) + 5)

    async def run():
        sender = object.__new__(MTProtoSender)
        sender._user_connected = True
        sender._reconnecting = False
        sender._connection = Connection()
        setattr(sender, '_state', State())
        sender._log = logger
        setattr(sender, '_start_reconnect', reconnect_errors.append)
        await sender._recv_loop()

    caplog.set_level(logging.WARNING, logger=logger.name)
    asyncio.run(run())

    assert len(reconnect_errors) == 1
    error = reconnect_errors[0]
    assert error.value_type == 'bytes'
    assert error.expected_length == len(secret) + 5
    assert error.available_length == len(secret)
    _assert_payload_is_absent(str(error), secret)
    _assert_payload_is_absent(repr(error), secret)
    _assert_payload_is_absent(caplog.text, secret)


def _malformed_gzip_packet(payload):
    return (
        struct.pack('<I', GzipPacked.CONSTRUCTOR_ID)
        + TLObject.serialize_bytes(payload)
    )


def test_malformed_gzip_error_exposes_only_safe_metadata():
    secret = b'Q7V4N2X9-gzip-sentinel-742b1d09'

    with pytest.raises(GzipPackedError) as raised:
        BinaryReader(_malformed_gzip_packet(secret)).tgread_object()

    error = raised.value
    assert error.compressed_length == len(secret)
    assert error.decompressor_error in {'BadGzipFile', 'error'}
    assert error.__cause__ is None
    assert error.__context__ is None
    rendered = ''.join((
        str(error), repr(error), repr(vars(error)),
        ''.join(traceback.format_exception(type(error), error, error.__traceback__)),
    ))
    _assert_payload_is_absent(rendered, secret)


def test_sender_receive_loop_malformed_gzip_is_sanitized(caplog):
    secret = b'recv-malformed-gzip-sentinel-c94f38a2'
    packet = _malformed_gzip_packet(secret)
    logger = logging.getLogger('telethon.layer231.safe-gzip-receive-path')
    reconnect_errors = []

    class Connection:
        @staticmethod
        async def recv():
            return packet

    class State:
        @staticmethod
        def decrypt_message_data(body):
            return BinaryReader(body).tgread_object()

    async def run():
        sender = object.__new__(MTProtoSender)
        sender._user_connected = True
        sender._reconnecting = False
        sender._connection = Connection()
        sender._state = State()
        sender._log = logger
        sender._start_reconnect = reconnect_errors.append
        await sender._recv_loop()

    caplog.set_level(logging.WARNING, logger=logger.name)
    asyncio.run(run())

    assert len(reconnect_errors) == 1
    error = reconnect_errors[0]
    assert isinstance(error, GzipPackedError)
    assert error.compressed_length == len(secret)
    assert error.__cause__ is None
    assert error.__context__ is None
    assert caplog.messages == [
        'Malformed gzip-packed data (length {} bytes, error {})'.format(
            len(secret), error.decompressor_error)]
    _assert_payload_is_absent(str(error), secret)
    _assert_payload_is_absent(repr(error), secret)
    _assert_payload_is_absent(caplog.text, secret)

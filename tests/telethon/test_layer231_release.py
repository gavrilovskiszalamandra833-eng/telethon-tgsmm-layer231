import asyncio
import logging
import struct
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from telethon.errors import TypeNotFoundError
from telethon.extensions import BinaryReader
from telethon.network.mtprotosender import MTProtoSender, _log_type_not_found
from telethon.tl import types
from telethon.tl.core import RpcResult


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

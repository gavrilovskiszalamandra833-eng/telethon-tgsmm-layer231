import asyncio
import json
import logging
import re
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
from telethon.client import telegrambaseclient
from telethon.client.telegrambaseclient import TelegramBaseClient
from telethon.tl import TLObject, alltlobjects, functions, types
from telethon.tl.core import GzipPacked, RpcResult
from telethon.tl.core.gzippacked import GzipPackedError
from telethon.version import __version__


ROOT = Path(__file__).resolve().parents[2]

CURRENT_CLIENT_DECLARATIONS = {
    'messageActionWalletTonConnectRequest': 'messageActionWalletTonConnectRequest#69b8c4bf flags:# accepted:flags.2?true declined:flags.3?true session_id:long expires:int topic:flags.0?string trace_id:flags.1?string dapp_name:flags.4?string = MessageAction;',
    'textTonAddress': 'textTonAddress#3cd2a36a text:RichText = RichText;',
    'updateSentWalletTransaction': 'updateSentWalletTransaction#b1434d4a flags:# gasless:flags.0?true msg_hash:string transaction:flags.1?WalletTransaction = Update;',
    'updateWalletGaslessInfo': 'updateWalletGaslessInfo#a8ae1cac flags:# available:flags.0?true left:int reset_at:int min_amount:long relayer_address:string = Update;',
    'updateWalletTonConnectSession': 'updateWalletTonConnectSession#50a38e0e session:TonConnectSession = Update;',
    'updateWalletTonConnectPendingDisconnect': 'updateWalletTonConnectPendingDisconnect#d1ee8199 session_ids:Vector<long> = Update;',
    'wallet.userAddresses': 'wallet.userAddresses#928e7b55 addresses:Vector<WalletUserAddress> users:Vector<User> = wallet.UserAddresses;',
    'walletTransactionPeerOnramp': 'walletTransactionPeerOnramp#e595186e flags:# address:string domain:flags.0?string provider_name:string = WalletTransactionPeer;',
    'wallet.proofChallenge': 'wallet.proofChallenge#99e41707 payload:string expires:int domain:string = wallet.ProofChallenge;',
    'walletOwnershipProof': 'walletOwnershipProof#60bccb0d timestamp:int signature:bytes = WalletOwnershipProof;',
    'tonConnectManifest': 'tonConnectManifest#12229264 flags:# url:string name:string icon:flags.0?WebDocument = TonConnectManifest;',
    'tonConnectSession': 'tonConnectSession#126556c6 flags:# pending:flags.0?true closing:flags.1?true closed:flags.2?true id:long dapp_client_id:string client_id:flags.3?string nonce:bytes manifest:flags.4?TonConnectManifest manifest_error:flags.5?int date:int = TonConnectSession;',
    'wallet.tonConnectChallenge': 'wallet.tonConnectChallenge#4bc89693 challenge:bytes event_id:long = wallet.TonConnectChallenge;',
    'tonConnectNextEventId': 'tonConnectNextEventId#582464e3 event_id:long = TonConnectNextEventId;',
    'tonConnectRequest': 'tonConnectRequest#a15f8513 flags:# session_id:long msg_id:int body:bytes expires:int topic:flags.0?string trace_id:flags.1?string = TonConnectRequest;',
    'wallet.tonConnectPending': 'wallet.tonConnectPending#85c0f124 session:TonConnectSession requests:Vector<TonConnectRequest> = wallet.TonConnectPending;',
    'wallet.tonConnectSessions': 'wallet.tonConnectSessions#e1f6896 sessions:Vector<TonConnectSession> = wallet.TonConnectSessions;',
    'wallet.existingBalance': 'wallet.existingBalance#bde90a8d flags:# has_balance:flags.0?true url:string = wallet.ExistingBalance;',
    'wallet.nftAttribute': 'wallet.nftAttribute#4c1ef10e trait_type:string value:string = wallet.NftAttribute;',
    'wallet.nftItem': 'wallet.nftItem#3441fd1c flags:# collection_address:flags.0?string address:string owner_address:string index:string name:flags.1?string description:flags.2?string image:flags.3?WebDocument image_small:flags.4?WebDocument content_url:flags.5?WebDocument lottie:flags.6?WebDocument attributes:flags.7?Vector<wallet.NftAttribute> extra:flags.8?DataJSON = wallet.NftItem;',
    'wallet.nftItems': 'wallet.nftItems#794d486f flags:# items:Vector<wallet.NftItem> next_offset:flags.0?string = wallet.NftItems;',
}

CURRENT_CLIENT_CLASSES = {
    'messageActionWalletTonConnectRequest': types.MessageActionWalletTonConnectRequest,
    'textTonAddress': types.TextTonAddress,
    'updateSentWalletTransaction': types.UpdateSentWalletTransaction,
    'updateWalletGaslessInfo': types.UpdateWalletGaslessInfo,
    'updateWalletTonConnectSession': types.UpdateWalletTonConnectSession,
    'updateWalletTonConnectPendingDisconnect': types.UpdateWalletTonConnectPendingDisconnect,
    'wallet.userAddresses': types.wallet.UserAddresses,
    'walletTransactionPeerOnramp': types.WalletTransactionPeerOnramp,
    'wallet.proofChallenge': types.wallet.ProofChallenge,
    'walletOwnershipProof': types.WalletOwnershipProof,
    'tonConnectManifest': types.TonConnectManifest,
    'tonConnectSession': types.TonConnectSession,
    'wallet.tonConnectChallenge': types.wallet.TonConnectChallenge,
    'tonConnectNextEventId': types.TonConnectNextEventId,
    'tonConnectRequest': types.TonConnectRequest,
    'wallet.tonConnectPending': types.wallet.TonConnectPending,
    'wallet.tonConnectSessions': types.wallet.TonConnectSessions,
    'wallet.existingBalance': types.wallet.ExistingBalance,
    'wallet.nftAttribute': types.wallet.NftAttribute,
    'wallet.nftItem': types.wallet.NftItem,
    'wallet.nftItems': types.wallet.NftItems,
}


def test_release_uses_canonical_distribution_identity():
    pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    setup_py = (ROOT / 'setup.py').read_text(encoding='utf-8')
    manifest = json.loads(
        (ROOT / 'generated-layer231-manifest.json').read_text(encoding='utf-8'))

    assert 'name = "Telethon"' in pyproject
    assert "name='Telethon'" in setup_py
    assert 'Telethon-TGSMM-Layer231' not in pyproject
    assert 'Telethon-TGSMM-Layer231' not in setup_py
    assert __version__ == '1.45.0+tgsmm.layer231.5'
    assert manifest['release'] == {
        'distribution': 'Telethon',
        'version': __version__,
    }


def _exported_sender_fixture(monkeypatch, *, send_error=None):
    sent = []
    connections = []

    class Sender:
        def __init__(self, auth_key, *, loggers):
            assert auth_key is None

        async def connect(self, connection):
            connections.append(connection)

        async def send(self, request):
            sent.append(request)
            if send_error is not None:
                raise send_error

    class Client:
        def __init__(self):
            self._proxy = ('proxy-host', 443)
            self._local_addr = ('127.0.0.1', 0)
            self._log = {telegrambaseclient.__name__: logging.getLogger(
                'telethon.layer231.exported-sender')}
            self._init_request = functions.InitConnectionRequest(
                api_id=12345,
                device_model='immutable-device',
                system_version='immutable-system',
                app_version='immutable-app',
                system_lang_code='immutable-system-lang',
                lang_pack='immutable-lang-pack',
                lang_code='immutable-lang',
                query=functions.help.GetConfigRequest(),
                proxy=object(),
                params=object(),
            )
            # Ensure cloning keeps the entire template, including attributes a
            # newer layer may add before this release helper is updated.
            self._init_request.release_marker = object()

        async def _get_dc(self, dc_id):
            return SimpleNamespace(
                id=dc_id, ip_address='149.154.167.{}'.format(dc_id), port=443)

        def _connection(self, *args, **kwargs):
            return args, kwargs

        async def __call__(self, request):
            await asyncio.sleep(0)
            return SimpleNamespace(
                id=request.dc_id,
                bytes='auth-{}'.format(request.dc_id).encode(),
            )

    monkeypatch.setattr(telegrambaseclient, 'MTProtoSender', Sender)
    return Client(), sent, connections


def _assert_export_uses_full_cloned_template(client, request, dc_id):
    assert isinstance(request, functions.InvokeWithLayerRequest)
    clone = request.query
    assert clone is not client._init_request
    assert clone.release_marker is client._init_request.release_marker
    for name, value in vars(client._init_request).items():
        if name != 'query':
            assert getattr(clone, name) is value or getattr(clone, name) == value
    assert isinstance(clone.query, functions.auth.ImportAuthorizationRequest)
    assert clone.query.id == dc_id
    assert clone.query.bytes == 'auth-{}'.format(dc_id).encode()


def test_exported_sender_clones_complete_init_connection_template(monkeypatch):
    client, sent, connections = _exported_sender_fixture(monkeypatch)
    original_query = client._init_request.query

    sender = asyncio.run(
        TelegramBaseClient._create_exported_sender(client, 2))

    assert sender is not None
    assert client._init_request.query is original_query
    assert len(sent) == len(connections) == 1
    _assert_export_uses_full_cloned_template(client, sent[0], 2)
    assert connections[0][1]['proxy'] is client._proxy
    assert connections[0][1]['local_addr'] is client._local_addr


@pytest.mark.parametrize('send_error', [RuntimeError('send failed'),
                                         asyncio.CancelledError()])
def test_exported_sender_failure_never_mutates_init_template(
        monkeypatch, send_error):
    client, sent, _ = _exported_sender_fixture(
        monkeypatch, send_error=send_error)
    original_query = client._init_request.query

    with pytest.raises(type(send_error)):
        asyncio.run(TelegramBaseClient._create_exported_sender(client, 3))

    assert client._init_request.query is original_query
    assert len(sent) == 1
    _assert_export_uses_full_cloned_template(client, sent[0], 3)


def test_concurrent_exported_senders_use_independent_init_clones(monkeypatch):
    client, sent, _ = _exported_sender_fixture(monkeypatch)
    original_query = client._init_request.query

    async def create_all():
        return await asyncio.gather(*(
            TelegramBaseClient._create_exported_sender(client, dc_id)
            for dc_id in (2, 3, 4, 5)))

    senders = asyncio.run(create_all())

    assert len(senders) == len(sent) == 4
    assert client._init_request.query is original_query
    assert len({id(request.query) for request in sent}) == 4
    for request in sent:
        _assert_export_uses_full_cloned_template(
            client, request, request.query.query.id)


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


def test_message_entity_ton_address_registry_and_roundtrip():
    constructor_id = 0xFDABBFCD
    assert types.MessageEntityTonAddress.CONSTRUCTOR_ID == constructor_id
    assert alltlobjects.tlobjects[constructor_id] is types.MessageEntityTonAddress

    entity = types.MessageEntityTonAddress(offset=4, length=48)
    assert bytes(entity) == struct.pack('<Iii', constructor_id, 4, 48)
    decoded_entity = _roundtrip(entity)
    assert isinstance(decoded_entity, types.MessageEntityTonAddress)
    assert decoded_entity.offset == 4
    assert decoded_entity.length == 48

    message = types.Message(
        id=231,
        peer_id=types.PeerUser(1001),
        date=datetime(2026, 10, 18, tzinfo=timezone.utc),
        message='TON UQ-address',
        entities=[entity],
    )
    decoded_message = _roundtrip(message)
    assert isinstance(decoded_message, types.Message)
    assert len(decoded_message.entities) == 1
    assert isinstance(decoded_message.entities[0], types.MessageEntityTonAddress)
    assert decoded_message.entities[0].offset == 4
    assert decoded_message.entities[0].length == 48


def _nested_vector_roundtrip(value):
    payload = struct.pack('<Ii', 0x1CB5C415, 1) + bytes(value)
    with BinaryReader(payload) as reader:
        decoded = reader.tgread_object()
        assert reader.tell_position() == len(payload)
    assert len(decoded) == 1
    return decoded[0]


def _current_client_fixtures():
    timestamp = datetime(2026, 10, 18, tzinfo=timezone.utc)
    manifest = types.TonConnectManifest(
        url='https://fixture.invalid/manifest.json', name='fixture-dapp')
    session = types.TonConnectSession(
        id=231, dapp_client_id='fixture-client', nonce=b'nonce',
        date=timestamp, manifest=manifest)
    request = types.TonConnectRequest(
        session_id=231, msg_id=5, body=b'fixture-body', expires=timestamp)
    attribute = types.wallet.NftAttribute(
        trait_type='fixture-trait', value='fixture-value')
    nft = types.wallet.NftItem(
        address='UQ-fixture-nft', owner_address='UQ-fixture-owner', index='1',
        attributes=[attribute])
    transaction = types.WalletTransaction(
        id='fixture-transaction', amount=7, fee=1, date=timestamp,
        peer=types.WalletTransactionPeerUnsupported())

    return {
        'messageActionWalletTonConnectRequest':
            types.MessageActionWalletTonConnectRequest(
                session_id=231, expires=timestamp, topic='fixture-topic'),
        'textTonAddress': types.TextTonAddress(types.TextPlain('UQ-fixture')),
        'updateSentWalletTransaction': types.UpdateSentWalletTransaction(
            msg_hash='fixture-hash', transaction=transaction),
        'updateWalletGaslessInfo': types.UpdateWalletGaslessInfo(
            left=3, reset_at=123, min_amount=10,
            relayer_address='UQ-fixture-relayer', available=True),
        'updateWalletTonConnectSession':
            types.UpdateWalletTonConnectSession(session),
        'updateWalletTonConnectPendingDisconnect':
            types.UpdateWalletTonConnectPendingDisconnect([231]),
        'wallet.userAddresses': types.wallet.UserAddresses(
            [types.WalletUserAddress(1001, 'UQ-fixture-address')], []),
        'walletTransactionPeerOnramp': types.WalletTransactionPeerOnramp(
            address='UQ-fixture-onramp', provider_name='fixture-provider'),
        'wallet.proofChallenge': types.wallet.ProofChallenge(
            payload='fixture-payload', expires=timestamp,
            domain='fixture.invalid'),
        'walletOwnershipProof': types.WalletOwnershipProof(
            timestamp=123, signature=b'fixture-signature'),
        'tonConnectManifest': manifest,
        'tonConnectSession': session,
        'wallet.tonConnectChallenge': types.wallet.TonConnectChallenge(
            challenge=b'fixture-challenge', event_id=9),
        'tonConnectNextEventId': types.TonConnectNextEventId(event_id=10),
        'tonConnectRequest': request,
        'wallet.tonConnectPending': types.wallet.TonConnectPending(
            session=session, requests=[request]),
        'wallet.tonConnectSessions': types.wallet.TonConnectSessions([session]),
        'wallet.existingBalance': types.wallet.ExistingBalance(
            url='https://fixture.invalid/balance', has_balance=True),
        'wallet.nftAttribute': attribute,
        'wallet.nftItem': nft,
        'wallet.nftItems': types.wallet.NftItems([nft], next_offset='fixture-next'),
    }


def test_current_client_incoming_compatibility_audit_is_21_of_21():
    schema_lines = {
        line.strip() for line in
        (ROOT / 'telethon_generator/data/api.tl').read_text(
            encoding='utf-8').splitlines()
    }
    fixtures = _current_client_fixtures()

    assert len(CURRENT_CLIENT_DECLARATIONS) == 21
    assert CURRENT_CLIENT_DECLARATIONS.keys() == CURRENT_CLIENT_CLASSES.keys()
    assert CURRENT_CLIENT_DECLARATIONS.keys() == fixtures.keys()
    for name, declaration in CURRENT_CLIENT_DECLARATIONS.items():
        cls = CURRENT_CLIENT_CLASSES[name]
        constructor_id = int(declaration.split('#', 1)[1].split()[0], 16)
        assert declaration in schema_lines
        assert cls.CONSTRUCTOR_ID == constructor_id
        assert alltlobjects.tlobjects[constructor_id] is cls


@pytest.mark.parametrize('name', CURRENT_CLIENT_DECLARATIONS)
def test_every_current_client_incoming_type_direct_and_nested_decodes(name):
    value = _current_client_fixtures()[name]
    cls = CURRENT_CLIENT_CLASSES[name]

    assert isinstance(_roundtrip(value), cls)
    assert isinstance(_nested_vector_roundtrip(value), cls)


def test_schema_and_generated_registry_have_no_duplicate_ids_or_names():
    declaration = re.compile(r'^([\w.]+)#([0-9a-fA-F]+)')
    entries = []
    for path in (
            ROOT / 'telethon_generator/data/api.tl',
            ROOT / 'telethon_generator/data/mtproto.tl'):
        for line in path.read_text(encoding='utf-8').splitlines():
            match = declaration.match(line.strip())
            if match:
                entries.append((match.group(1), int(match.group(2), 16)))

    names = [name for name, _ in entries]
    constructor_ids = [constructor_id for _, constructor_id in entries]
    assert len(names) == len(set(names))
    assert len(constructor_ids) == len(set(constructor_ids))

    generated_classes = list(alltlobjects.tlobjects.values())
    generated_names = [
        '{}.{}'.format(cls.__module__, cls.__qualname__)
        for cls in generated_classes
    ]
    assert len(alltlobjects.tlobjects) == len(set(alltlobjects.tlobjects))
    assert len(generated_classes) == len(set(generated_classes))
    assert len(generated_names) == len(set(generated_names))


@pytest.mark.parametrize(('canonical', 'compatibility', 'canonical_id', 'compatibility_id'), [
    (types.UserFull, types.UserFullCurrentClientCompat, 0x7FE738C4, 0x06CBE645),
    (types.WalletUserAddress, types.WalletUserAddressCurrentClientCompat,
     0x1CE00108, 0xFE78EECC),
    (types.WalletTransaction, types.WalletTransactionCurrentClientCompat,
     0x6F9986A1, 0x952DC143),
])
def test_recycled_response_ids_coexist_and_decode_nested(
        canonical, compatibility, canonical_id, compatibility_id):
    timestamp = datetime(2026, 10, 18, tzinfo=timezone.utc)
    peer = types.WalletTransactionPeerUnsupported()
    if canonical is types.UserFull:
        canonical_value = canonical(
            id=1001, settings=types.PeerSettings(),
            notify_settings=types.PeerNotifySettings(), common_chats_count=0,
            gram_address='UQ-layer231')
        compatibility_value = compatibility(
            id=1001, settings=types.PeerSettings(),
            notify_settings=types.PeerNotifySettings(), common_chats_count=0)
    elif canonical is types.WalletUserAddress:
        canonical_value = canonical(1001, 'UQ-layer231')
        compatibility_value = compatibility(
            address='UQ-current-client', public_key=b'fixture-public-key',
            user_id=1001)
    else:
        canonical_value = canonical(
            id='layer231', amount=5, fee=1, date=timestamp, peer=peer)
        compatibility_value = compatibility(
            id='current-client', amount=6, fee=1, date=timestamp, peer=peer,
            gasless=True)

    assert canonical.CONSTRUCTOR_ID == canonical_id
    assert compatibility.CONSTRUCTOR_ID == compatibility_id
    assert alltlobjects.tlobjects[canonical_id] is canonical
    assert alltlobjects.tlobjects[compatibility_id] is compatibility
    assert isinstance(_roundtrip(canonical_value), canonical)
    assert isinstance(_roundtrip(compatibility_value), compatibility)
    assert isinstance(_nested_vector_roundtrip(canonical_value), canonical)
    assert isinstance(_nested_vector_roundtrip(compatibility_value), compatibility)

    if canonical is types.UserFull:
        canonical_parent = types.users.UserFull(canonical_value, [], [])
        compatibility_parent = types.users.UserFull(compatibility_value, [], [])
        canonical_nested = _roundtrip(canonical_parent).full_user
        compatibility_nested = _roundtrip(compatibility_parent).full_user
    elif canonical is types.WalletUserAddress:
        canonical_parent = types.wallet.UserAddresses([canonical_value], [])
        compatibility_parent = types.wallet.UserAddresses(
            [compatibility_value], [])
        canonical_nested = _roundtrip(canonical_parent).addresses[0]
        compatibility_nested = _roundtrip(compatibility_parent).addresses[0]
    else:
        canonical_parent = types.UpdateSentWalletTransaction(
            msg_hash='canonical-fixture', transaction=canonical_value)
        compatibility_parent = types.UpdateSentWalletTransaction(
            msg_hash='compatibility-fixture', transaction=compatibility_value)
        canonical_nested = _roundtrip(canonical_parent).transaction
        compatibility_nested = _roundtrip(compatibility_parent).transaction

    assert isinstance(canonical_nested, canonical)
    assert isinstance(compatibility_nested, compatibility)


@pytest.mark.parametrize(('name', 'constructor_id'), [
    ('MessageActionGramTransfer', 0x9329EA33),
    ('UpdateWalletState', 0x6AC3F2AA),
    ('UserFull', 0x7FE738C4),
    ('BotVerification', 0xF72E0ED9),
])
def test_layer231_constructor_ids(name, constructor_id):
    assert getattr(types, name).CONSTRUCTOR_ID == constructor_id


def test_regeneration_preserves_patched_message_registry():
    assert types.Message.__module__ == 'telethon.tl.patched'
    assert alltlobjects.tlobjects[types.Message.CONSTRUCTOR_ID] is types.Message


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

Layer 231 fork release notes
============================

Identity
--------

This repository is an audited Git-dependency fork of Telethon. It installs as
the canonical ``Telethon`` distribution and retains the ``telethon`` import
package. Its unique PEP 440 version is ``1.45.0+tgsmm.layer231.5``. Using the
canonical distribution name lets requirements such as
``opentele-ng``'s ``telethon>=1.36,<2`` resolve to this fork without installing
a second distribution that also owns the ``telethon`` namespace. Consumers
should pin the release tag or commit.

Provenance
----------

* Exact upstream base: ``bad095bd5b3dc9f852cfbeeba300a421169c9b1e``
  (upstream Telethon ``v1.45.0``).
* Layer: ``231``.
* ``telethon_generator/data/api.tl`` SHA-256:
  ``2af6dbc782deffa3e4a1d9cb3dce6877777ed303d9779d64d9af41495ef38f05``.
* The layer 231 schema changes are client-derived and unofficial. They are not
  represented as an upstream Telegram-published schema and must not be
  described as upstream-authored or upstream-supported.

Generation and expected inventory
---------------------------------

Run the canonical generator from the repository root::

    python3 setup.py gen tl errors

The checked-in result is expected to contain:

* 1,750 constructors;
* 841 functions;
* 2,591 total TL objects;
* 533 generated RPC error definitions; and
* 57 generated Python files: ``telethon/tl/alltlobjects.py``,
  ``telethon/errors/rpcerrorlist.py``, and every ``*.py`` file under
  ``telethon/tl/types/`` and ``telethon/tl/functions/``.

``generated-layer231-manifest.json`` records every generator input and every
committed runtime output by path and SHA-256. Verify a clean deterministic
regeneration with::

    python3 scripts/check_generated.py --regenerate
    git diff --exit-code

Only use ``python3 scripts/check_generated.py --update`` when intentionally
changing the schema, generator, or generated artifacts; review the resulting
manifest diff together with the generated code.

Verification
------------

The upstream test suite remains present under ``tests/``. Run the layer 231
fixtures and the complete upstream suite with::

    python3 -m pytest -q tests/telethon/test_layer231_release.py
    python3 -m pytest -q
    uv build

In a clean environment, install ``opentele-ng`` and the fork wheel, then run
``python -m pip check``. ``importlib.metadata`` must report exactly one
distribution providing the ``telethon`` package, named ``Telethon`` at version
``1.45.0+tgsmm.layer231.5``.

Exported senders clone the complete client ``InitConnection`` template before
installing their ``auth.importAuthorization`` query. Borrowing one or several
data-center senders therefore cannot replace the shared template query or lose
its proxy, device, application, system, language, or client-parameter metadata,
including when an import fails or is cancelled.

Build 4 added the live-proven ``messageEntityTonAddress#fdabbfcd`` declaration.
Build 5 adds the other 21 unique incoming object constructors found in the
current Telegram Desktop and TDLib schema snapshots, including wallet,
TonConnect, NFT, update, rich-text, and message-action objects. The declarations
were reconciled against Telegram Desktop commit
``d36272b193057a114ef3a9fe7f15a8f8b587c489`` and the matching TDLib schema.
This is a current-client incoming decode compatibility superset of layer 231;
it is not layer 232 and makes no generic forward-compatibility claim. No
request-only methods were imported.

Three uniquely named, decode-only compatibility predicates preserve recycled
response IDs alongside the canonical layer-231 forms:
``UserFullCurrentClientCompat#06cbe645``,
``WalletUserAddressCurrentClientCompat#fe78eecc``, and
``WalletTransactionCurrentClientCompat#952dc143``. The layer-231 constructors
remain registered at ``#7fe738c4``, ``#1ce00108``, and ``#6f9986a1``. The
generator's layer-specific ID-mismatch allowlist is itself included in the
deterministic source manifest.

Release tests audit all 21 declarations and registry mappings, directly decode
and vector-nest every added type, decode both IDs in all three recycled-ID
pairs, and reject duplicate schema IDs, schema names, generated classes, or
fully qualified generated class names.

The release fixtures cover the patched ``MessageService`` class carrying
``MessageActionGramTransfer``, ``UpdateWalletState``, ``UserFull.gram_address``,
and ``BotVerification.description`` as ``TextWithEntities``. A release wheel
must contain the complete ``telethon`` import package, including the generated
layer 231 files. Security tests also require unknown-constructor,
truncated-reader, invalid-buffer, sender-exception, and orphan-response
diagnostics to contain only safe metadata (value type, expected/available
lengths, and constructor ID where available), never raw payload bytes or their
repr.

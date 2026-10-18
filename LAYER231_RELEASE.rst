Layer 231 fork release notes
============================

Identity
--------

This repository is an internal, Git-dependency fork of Telethon. It installs
as the distinct distribution ``Telethon-TGSMM-Layer231`` while retaining the
``telethon`` import package. Its PEP 440 version is
``1.45.0+tgsmm.layer231.1``. Consumers should pin the release commit in their
Git dependency rather than resolve it as upstream ``Telethon``.

Provenance
----------

* Exact upstream base: ``bad095bd5b3dc9f852cfbeeba300a421169c9b1e``
  (upstream Telethon ``v1.45.0``).
* Layer: ``231``.
* ``telethon_generator/data/api.tl`` SHA-256:
  ``3631e910da8b2f902b29247f29fd1233d217075222a7d448bb28ef726c508576``.
* The layer 231 schema changes are client-derived and unofficial. They are not
  represented as an upstream Telegram-published schema and must not be
  described as upstream-authored or upstream-supported.

Generation and expected inventory
---------------------------------

Run the canonical generator from the repository root::

    python3 setup.py gen tl errors

The checked-in result is expected to contain:

* 1,725 constructors;
* 841 functions;
* 2,566 total TL objects;
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

The release fixtures cover the patched ``MessageService`` class carrying
``MessageActionGramTransfer``, ``UpdateWalletState``, ``UserFull.gram_address``,
and ``BotVerification.description`` as ``TextWithEntities``. A release wheel
must contain the complete ``telethon`` import package, including the generated
layer 231 files. Security tests also require unknown-constructor,
truncated-reader, invalid-buffer, sender-exception, and orphan-response
diagnostics to contain only safe metadata (value type, expected/available
lengths, and constructor ID where available), never raw payload bytes or their
repr.

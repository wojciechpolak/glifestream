from __future__ import annotations

import importlib
import sys


def test_factory_import_keeps_atproto_client_lazy():
    sys.modules.pop('glifestream.apis.factory', None)

    atproto_module = importlib.import_module('glifestream.apis.atproto')
    atproto_module = importlib.reload(atproto_module)
    assert atproto_module.Client is None

    factory_module = importlib.import_module('glifestream.apis.factory')
    factory_module = importlib.reload(factory_module)

    assert factory_module.ServiceFactory.get_service_class('atproto') is atproto_module.AtProtoService
    assert atproto_module.Client is None

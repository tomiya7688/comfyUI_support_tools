"""Tests for the reversible Python 3.10 certifi TLS shim."""

from __future__ import annotations

import importlib.util
import runpy
import ssl
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tools.security import python310_tls_shim


# {
#   責務: [Python310TlsShimTest: Python 3.10 TLS shimのfactory置換とinstaller保護を検証する]
#   フィールド: []
#   処理: [ssl factoryの挙動、失敗時のfail-closed、管理外ファイルの保護を確認する]
# }
class Python310TlsShimTest(unittest.TestCase):
    # {
    #   責務: [test_default_server_context_uses_certifi_and_explicit_ca_is_preserved: 既定server contextへcertifiを使い明示CA指定を保つ]
    #   処理: [1: ssl factoryを記録するfakeへshimを適用する, 2: 既定/明示指定の呼び出し結果を検証する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_default_server_context_uses_certifi_and_explicit_ca_is_preserved(self):
        calls: list[tuple[object, dict[str, object]]] = []

        # {
        #   責務: [create_default_context: fake ssl factoryの引数を記録する]
        #   処理: [1: server-auth purposeとCA指定を記録する, 2: 記録した呼び出しを返す]
        #   引数: [purpose: TLS contextの用途, cafile: CA bundle, capath: CA directory, cadata: CA data]
        #   戻り値: [call: 記録したfactory引数]
        # }
        def create_default_context(purpose, *, cafile=None, capath=None, cadata=None):
            calls.append((purpose, {"cafile": cafile, "capath": capath, "cadata": cadata}))
            return calls[-1]

        fake_ssl = SimpleNamespace(
            Purpose=ssl.Purpose,
            create_default_context=create_default_context,
            _create_default_https_context=create_default_context,
        )

        python310_tls_shim.install_certifi_default_context(fake_ssl, "certifi/cacert.pem")

        fake_ssl.create_default_context()
        fake_ssl.create_default_context(cafile="custom.pem")

        self.assertEqual(calls[0][1]["cafile"], "certifi/cacert.pem")
        self.assertEqual(calls[1][1]["cafile"], "custom.pem")
        self.assertIs(fake_ssl._create_default_https_context, fake_ssl.create_default_context)

    # {
    #   責務: [test_sitecustomize_fails_closed_when_helper_is_missing: startup shim欠落時にTLSを閉じる]
    #   処理: [1: Python 3.10 startup条件とmissing helperを隔離して再現する, 2: 既定TLS factoryが拒否へ差し替わったことを検証する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_sitecustomize_fails_closed_when_helper_is_missing(self):
        source = Path(__file__).resolve().parents[3] / "tools" / "security" / "sitecustomize.py"
        fake_ssl = SimpleNamespace(
            SSLError=RuntimeError,
            create_default_context=lambda: "unsafe",
            _create_default_https_context=lambda: "unsafe",
        )
        fake_certifi = SimpleNamespace(where=lambda: "unused.pem")

        with (
            patch.object(sys, "implementation", SimpleNamespace(name="cpython")),
            patch.object(sys, "version_info", (3, 10, 11)),
            patch.dict(
                "sys.modules",
                {"ssl": fake_ssl, "certifi": fake_certifi, "python310_tls_shim": None},
            ),
        ):
            runpy.run_path(source)
            with self.assertRaisesRegex(RuntimeError, "Python 3.10 TLS blocked"):
                fake_ssl.create_default_context()

    # {
    #   責務: [test_installer_refuses_to_overwrite_unmanaged_sitecustomize: 管理外のsitecustomizeを上書きしない]
    #   処理: [1: installer moduleを隔離して読み込む, 2: 管理外fileを表すfake pathを作る, 3: validatorが拒否することを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_installer_refuses_to_overwrite_unmanaged_sitecustomize(self):
        source = Path(__file__).resolve().parents[3] / "tools" / "security"
        spec = importlib.util.spec_from_file_location(
            "install_python310_tls_shim_test_target",
            source / "install_python310_tls_shim.py",
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)

        unmanaged = MagicMock(spec=Path)
        unmanaged.exists.return_value = True
        unmanaged.read_text.return_value = "# user-owned\n"
        unmanaged.__str__.return_value = "venv/site-packages/sitecustomize.py"

        with self.assertRaises(FileExistsError):
            installer.validate_managed_target(unmanaged)
        unmanaged.unlink.assert_not_called()


if __name__ == "__main__":
    unittest.main()

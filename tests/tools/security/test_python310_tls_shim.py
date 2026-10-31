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
        fake_ssl.create_default_context(cafile="", capath="", cadata="")
        fake_ssl.create_default_context(cafile="custom.pem")

        self.assertEqual(calls[0][1]["cafile"], "certifi/cacert.pem")
        self.assertEqual(calls[0][0], ssl.Purpose.SERVER_AUTH)
        self.assertEqual(calls[1][1]["cafile"], "certifi/cacert.pem")
        self.assertEqual(calls[2][1]["cafile"], "custom.pem")
        self.assertIs(fake_ssl._create_default_https_context, fake_ssl.create_default_context)

    # {
    #   責務: [test_captured_factory_references_are_replaced: startup前に保持されたfactory参照も差し替える]
    #   処理: [1: fake consumerへ元factoryを保持する, 2: shim適用後に参照先が変わったことを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_captured_factory_references_are_replaced(self):
        # {
        #   責務: [create_default_context: fake factoryの呼出引数を返す]
        #   処理: [purposeとCA指定をtupleにして返す]
        #   引数: [args: 位置引数, kwargs: 名前付き引数]
        #   戻り値: [call: 渡された引数]
        # }
        def create_default_context(*args, **kwargs):
            return args, kwargs

        consumer = SimpleNamespace(create_default_context=create_default_context)
        with patch.dict(sys.modules, {"_tls_consumer_test": consumer}):
            fake_ssl = SimpleNamespace(
                Purpose=ssl.Purpose,
                create_default_context=create_default_context,
                _create_default_https_context=create_default_context,
            )
            python310_tls_shim.install_certifi_default_context(fake_ssl, "certifi/cacert.pem")

        self.assertIs(consumer.create_default_context, fake_ssl.create_default_context)

    # {
    #   責務: [test_sitecustomize_fails_closed_when_helper_is_missing: startup shim欠落時にTLSを閉じる]
    #   処理: [1: Python 3.10 startup条件とmissing helperを隔離して再現する, 2: 既定TLS factoryが拒否へ差し替わったことを検証する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_sitecustomize_fails_closed_when_helper_is_missing(self):
        source = Path(__file__).resolve().parents[3] / "tools" / "security" / "sitecustomize.py"

        # {
        #   責務: [create_default_context: fake factoryの呼出引数を返す]
        #   処理: [purposeとCA指定をtupleにして返す]
        #   引数: [purpose: TLS context用途, cafile: CA bundle, capath: CA directory, cadata: CA data]
        #   戻り値: [call: 渡された引数]
        # }
        def create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None
        ):
            return (purpose, cafile, capath, cadata)

        fake_ssl = SimpleNamespace(
            SSLError=RuntimeError,
            Purpose=ssl.Purpose,
            create_default_context=create_default_context,
            _create_default_https_context=create_default_context,
        )
        fake_certifi = SimpleNamespace(where=lambda: "unused.pem")
        captured_factory = SimpleNamespace(create_default_context=create_default_context)

        with (
            patch.object(sys, "implementation", SimpleNamespace(name="cpython")),
            patch.object(sys, "version_info", (3, 10, 11)),
            patch.dict(
                sys.modules,
                {
                    "ssl": fake_ssl,
                    "certifi": fake_certifi,
                    "python310_tls_shim": None,
                    "_tls_captured_factory_test": captured_factory,
                },
            ),
        ):
            runpy.run_path(source)
            with self.assertRaisesRegex(RuntimeError, "Python 3.10 TLS blocked"):
                fake_ssl.create_default_context()
            self.assertEqual(fake_ssl.create_default_context(cafile="custom.pem")[1], "custom.pem")
            self.assertIs(captured_factory.create_default_context, fake_ssl.create_default_context)

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

    # {
    #   責務: [test_installer_validates_ca_bundle: installerが共通CA検査に失敗したbundleを拒否する]
    #   処理: [1: checkerが失敗する結果を返すようにする, 2: actionable errorを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_installer_validates_ca_bundle(self):
        source = Path(__file__).resolve().parents[3] / "tools" / "security"
        spec = importlib.util.spec_from_file_location(
            "install_python310_tls_shim_ca_test_target",
            source / "install_python310_tls_shim.py",
        )
        self.assertIsNotNone(spec)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        result = SimpleNamespace(returncode=1, stdout="FAIL: stale certifi", stderr="")
        with patch.object(installer.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "Upgrade pip and certifi"):
                installer.validate_certifi_bundle()

    # {
    #   責務: [test_installer_detects_shadowing_sitecustomize: 先行sitecustomizeがある場合にinstallerを止める]
    #   処理: [1: sys.path先頭に競合sitecustomizeを作る, 2: resolverが拒否することを確認する]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_installer_detects_shadowing_sitecustomize(self):
        source = Path(__file__).resolve().parents[3] / "tools" / "security"
        spec = importlib.util.spec_from_file_location(
            "install_python310_tls_shim_shadow_test_target",
            source / "install_python310_tls_shim.py",
        )
        self.assertIsNotNone(spec)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with patch("sys.path", ["shadow", "managed"]):
            with patch.object(
                Path,
                "is_file",
                autospec=True,
                side_effect=lambda path: (
                    path.name == "sitecustomize.py" and path.parent.name == "shadow"
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "shadows"):
                    installer.validate_startup_resolution(Path("managed"))

    # {
    #   責務: [test_installer_ignores_its_source_path: installer自身のscript directoryを通常のshadowとして扱わない]
    #   処理: [1: installer source directoryをsys.path先頭に置く, 2: 別のshadowがない場合に検証を通す]
    #   引数: [self: unittest test case]
    #   戻り値: []
    # }
    def test_installer_ignores_its_source_path(self):
        source = Path(__file__).resolve().parents[3] / "tools" / "security"
        spec = importlib.util.spec_from_file_location(
            "install_python310_tls_shim_source_path_test_target",
            source / "install_python310_tls_shim.py",
        )
        self.assertIsNotNone(spec)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with patch("sys.path", [str(source), "managed"]):
            with patch.object(
                Path,
                "is_file",
                autospec=True,
                side_effect=lambda path: (
                    path.name == "sitecustomize.py" and path.parent == source.resolve()
                ),
            ):
                installer.validate_startup_resolution(Path("managed"))


if __name__ == "__main__":
    unittest.main()

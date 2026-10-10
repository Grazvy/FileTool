"""The macOS app builder: what goes into the bundle, and the icon.

Running PyInstaller itself takes minutes, so the suite checks everything the
builder decides — the Info.plist that puts File Tool in "Open with", and the
spec that carries it — and leaves the packaging to the build command.
"""

import ast
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from tools import build_macos, icon

macos_only = pytest.mark.skipif(sys.platform != "darwin", reason="macOS packaging only")


# ---------- what the bundle declares ----------


def test_the_app_offers_to_open_every_supported_format():
    types = build_macos.info_plist()["CFBundleDocumentTypes"]
    declared = {utis for kind in types for utis in kind["LSItemContentTypes"]}
    assert declared == {"com.adobe.pdf", "public.png", "public.jpeg"}


def test_the_app_is_an_option_rather_than_the_default_handler():
    """"Alternate" lists File Tool in "Open with" without taking PDFs over."""
    for kind in build_macos.info_plist()["CFBundleDocumentTypes"]:
        assert kind["LSHandlerRank"] == "Alternate"
        assert kind["CFBundleTypeRole"] == "Editor"


def test_the_app_has_no_dock_icon():
    """It is a server behind a browser tab, so an idle Dock icon would be a lie."""
    assert build_macos.info_plist()["LSUIElement"] is True


def test_the_plist_is_writable_as_a_plist():
    """PyInstaller writes this dictionary out, so it must survive the trip."""
    written = plistlib.loads(plistlib.dumps(build_macos.info_plist()))
    assert written["CFBundleIdentifier"] == build_macos.BUNDLE_ID
    assert len(written["CFBundleDocumentTypes"]) == 3


# ---------- the spec handed to PyInstaller ----------


def test_the_spec_is_valid_python():
    ast.parse(build_macos.spec_text(Path("/tmp/FileTool.icns")))


def test_the_spec_bundles_the_frontend():
    """Without the frontend in the bundle the app starts and serves nothing."""
    assert '"frontend"' in build_macos.spec_text(None)


def test_the_spec_carries_the_document_types():
    assert "com.adobe.pdf" in build_macos.spec_text(None)


def test_the_spec_leaves_the_opened_files_to_the_app():
    """The bootloader's argv emulation would swallow all but the first file."""
    assert "argv_emulation=False" in build_macos.spec_text(None)


def test_the_spec_names_the_icon_when_there_is_one():
    assert "FileTool.icns" in build_macos.spec_text(Path("/tmp/FileTool.icns"))
    assert "icon=None" in build_macos.spec_text(None)


def test_the_spec_hides_nothing_uvicorn_needs_at_runtime():
    spec = build_macos.spec_text(None)
    assert "uvicorn.protocols.http.auto" in spec
    assert "uvicorn.lifespan.on" in spec


# ---------- the icon ----------


def test_the_icon_is_drawn_square_and_opaque_in_the_middle():
    art = icon.draw(size=128)
    assert art.size == (128, 128)
    assert art.getpixel((64, 64))[3] == 255


def test_the_icon_corners_are_rounded_away():
    assert icon.draw(size=128).getpixel((1, 1))[3] == 0


def test_the_iconset_holds_every_size_at_both_scales(tmp_path):
    iconset = icon.write_iconset(tmp_path, size=128)
    written = sorted(path.name for path in iconset.glob("*.png"))
    assert len(written) == len(icon.ICONSET_SIZES) * 2
    assert "icon_512x512@2x.png" in written
    assert Image.open(iconset / "icon_32x32@2x.png").size == (64, 64)


@macos_only
def test_the_icns_is_built_by_iconutil(tmp_path):
    icns = icon.build_icns(tmp_path)
    assert icns.is_file()
    assert icns.read_bytes()[:4] == b"icns"


# ---------- installing ----------


def test_install_puts_the_app_where_macos_looks(tmp_path, monkeypatch):
    registered, unregistered = [], []
    monkeypatch.setattr(build_macos, "register", registered.append)
    monkeypatch.setattr(build_macos, "unregister", unregistered.append)
    bundle = tmp_path / "FileTool.app"
    (bundle / "Contents").mkdir(parents=True)
    (bundle / "Contents" / "Info.plist").write_text("x")

    applications = tmp_path / "Applications"
    applications.mkdir()
    installed = build_macos.install(bundle, applications=applications)

    assert installed == applications / "FileTool.app"
    assert (installed / "Contents" / "Info.plist").read_text() == "x"
    assert registered == [installed]
    # Only the installed copy may stay in "Open with", so removing it removes File Tool.
    assert unregistered == [bundle]


def test_install_replaces_an_older_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(build_macos, "register", lambda target: None)
    monkeypatch.setattr(build_macos, "unregister", lambda bundle: None)
    bundle = tmp_path / "FileTool.app"
    bundle.mkdir()
    (bundle / "new").write_text("new")

    applications = tmp_path / "Applications"
    (applications / "FileTool.app").mkdir(parents=True)
    (applications / "FileTool.app" / "stale").write_text("stale")

    installed = build_macos.install(bundle, applications=applications)
    assert (installed / "new").exists()
    assert not (installed / "stale").exists()


def test_install_falls_back_to_the_users_own_applications(tmp_path, monkeypatch):
    """Without an administrator password /Applications is not writable."""
    monkeypatch.setattr(build_macos, "register", lambda target: None)
    monkeypatch.setattr(build_macos, "unregister", lambda bundle: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")

    def refuse(bundle, target):
        if "home" not in str(target):
            raise PermissionError(target)
        build_macos.shutil.copytree(bundle, target, symlinks=True)

    monkeypatch.setattr(build_macos, "_replace", refuse)
    bundle = tmp_path / "FileTool.app"
    bundle.mkdir()

    installed = build_macos.install(bundle, applications=Path("/Applications"))
    assert installed == tmp_path / "home" / "Applications" / "FileTool.app"


def test_a_failed_registration_is_reported_and_survived(monkeypatch, capsys):
    """A registered app is a convenience; failing to register is not fatal."""
    def explode(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "lsregister")

    monkeypatch.setattr(build_macos.subprocess, "run", explode)
    build_macos.register(Path("/Applications/FileTool.app"))
    assert "Could not register" in capsys.readouterr().err


def test_unregistering_a_copy_that_was_never_registered_is_quiet(monkeypatch, capsys):
    """lsregister -u fails for an unknown copy, which is the state asked for."""
    def not_registered(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "lsregister")

    monkeypatch.setattr(build_macos.subprocess, "run", not_registered)
    build_macos.unregister(Path("dist/FileTool.app"))
    assert capsys.readouterr().err == ""


def test_a_missing_lsregister_is_reported_when_unregistering(monkeypatch, capsys):
    def missing(*args, **kwargs):
        raise FileNotFoundError("lsregister")

    monkeypatch.setattr(build_macos.subprocess, "run", missing)
    build_macos.unregister(Path("dist/FileTool.app"))
    assert "Could not unregister" in capsys.readouterr().err

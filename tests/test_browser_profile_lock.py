from __future__ import annotations

import os

from autofag.auth.browser import release_stale_profile_lock

SINGLETONS = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def _make_profile(tmp_path, pid: int):
    profile = tmp_path / "profile"
    profile.mkdir()
    for name in SINGLETONS:
        (profile / name).unlink(missing_ok=True)
    os.symlink(f"somehost-{pid}", profile / "SingletonLock")
    (profile / "SingletonCookie").write_text("x", encoding="utf-8")
    (profile / "SingletonSocket").write_text("x", encoding="utf-8")
    return profile


def test_a_stale_lock_from_a_dead_process_is_cleared(tmp_path):
    profile = _make_profile(tmp_path, pid=999999)

    assert release_stale_profile_lock(profile) is None
    assert not (profile / "SingletonLock").is_symlink()
    assert not (profile / "SingletonCookie").exists()


def test_a_live_process_keeps_its_lock_and_is_named(tmp_path):
    profile = _make_profile(tmp_path, pid=os.getpid())

    assert release_stale_profile_lock(profile) == os.getpid()
    assert (profile / "SingletonLock").is_symlink()


def test_a_profile_without_a_lock_is_left_alone(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()

    assert release_stale_profile_lock(profile) is None

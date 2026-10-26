"""模型登记表的读缓存：文件没变不重读；手改了、别的进程写了、自己写了都立刻看得到；用的人改返回值带不坏缓存。"""

from __future__ import annotations

import json
import os

import pytest

from app.repository.provider_repository import ModelProviderRegistry


def provider(model_id="m", **extra):
    return {
        "name": model_id, "served_model_id": model_id, "base_url": "http://127.0.0.1:9/v1",
        "upstream_model": "u", "auth_mode": "none", "api_key": "", "enabled": True, **extra,
    }


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def registry(tmp_path, clock):
    instance = ModelProviderRegistry(tmp_path / "providers.json", clock=clock)
    instance.create_provider(provider("m", extra_body={"thinking": {"type": "disabled"}}))
    return instance


def count_loads(registry, monkeypatch):
    loads = []
    real = registry._load_unlocked

    def counting():
        loads.append(1)
        return real()

    monkeypatch.setattr(registry, "_load_unlocked", counting)
    return loads


def test_an_unchanged_file_is_not_read_again(registry, monkeypatch):
    loads = count_loads(registry, monkeypatch)
    for _ in range(20):
        registry.get_enabled_provider("m")
        registry.list_providers()
        registry.get_default_model_id()
    assert len(loads) == 1


def test_a_hand_edit_of_the_file_shows_up_within_a_second(registry, clock):
    registry.get_enabled_provider("m")
    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["providers"][0]["name"] = "手改过的名字"
    registry.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    stat = registry.path.stat()
    os.utime(registry.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert registry.get_enabled_provider("m").name == "m", "一秒之内不去看文件"
    clock.now += 1.5
    assert registry.get_enabled_provider("m").name == "手改过的名字"


def test_the_file_is_not_even_looked_at_more_than_once_a_second(registry, clock, monkeypatch):
    registry.get_enabled_provider("m")
    looks = []
    real_stat = type(registry.path).stat

    def counting_stat(self, *args, **kwargs):
        looks.append(1)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(type(registry.path), "stat", counting_stat)
    for _ in range(50):
        registry.get_enabled_provider("m")
    assert looks == []
    clock.now += 1.5
    registry.get_enabled_provider("m")
    assert len(looks) == 1


def test_its_own_writes_are_visible_immediately(registry):
    registry.get_enabled_provider("m")
    registry.create_provider(provider("n"))
    assert {item["served_model_id"] for item in registry.list_providers()} == {"m", "n"}
    registry.update_provider("n", {"enabled": False})
    with pytest.raises(KeyError):
        registry.get_enabled_provider("n")


def test_changing_what_a_read_returns_does_not_change_the_registry(registry):
    first = registry.get_enabled_provider("m")
    first.extra_body["thinking"]["type"] = "enabled"
    registry.list_providers()[0]["name"] = "改掉"
    second = registry.get_enabled_provider("m")
    assert second.extra_body == {"thinking": {"type": "disabled"}} and second.name == "m"


def test_a_rejected_write_leaves_the_cached_registry_alone(registry):
    registry.get_enabled_provider("m")
    with pytest.raises(ValueError):
        registry.update_provider("m", {"temperature": 99})
    assert registry.get_enabled_provider("m").temperature == 0.1


def test_a_deleted_file_reads_as_empty(registry, clock):
    registry.get_enabled_provider("m")
    registry.path.unlink()
    clock.now += 1.5
    assert registry.list_providers() == []


def test_a_write_that_fails_halfway_does_not_leak_into_later_reads(registry, monkeypatch):
    """写的方法会就地改读出来的内容（加一条、修默认模型），写盘失败时那份改动不能留在缓存里。"""
    registry.get_enabled_provider("m")

    def broken_replace(*_args, **_kwargs):
        raise OSError("磁盘满了")

    monkeypatch.setattr("app.repository.provider_repository.os.replace", broken_replace)
    with pytest.raises(OSError):
        registry.create_provider(provider("n"))
    monkeypatch.undo()
    assert [item["served_model_id"] for item in registry.list_providers()] == ["m"]


def test_a_damaged_file_is_reported_every_time_not_hidden_by_the_last_good_copy(registry, clock):
    from app.errors.registry_errors import RegistryLoadError

    registry.get_enabled_provider("m")
    registry.path.write_text("{ 坏掉的 JSON", encoding="utf-8")
    clock.now += 1.5
    for _ in range(3):
        with pytest.raises(RegistryLoadError):
            registry.list_providers()

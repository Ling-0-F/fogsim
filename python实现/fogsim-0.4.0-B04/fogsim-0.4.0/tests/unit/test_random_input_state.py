from dataclasses import fields, replace, FrozenInstanceError
import random
import pytest
from fogsim import prepare_random_input, load_experiment_config
from fogsim.errors import InputError
from fogsim.experiment_config import WorkflowTypeRange, RepeatConfig
from fogsim.seed import encode_seed
from conftest import ROOT


def config(seed=0):
    cfg = load_experiment_config(ROOT / "configs/examples/step1_dynamic.json")
    return replace(cfg, source=replace(cfg.source, seed=seed, workflow_types=WorkflowTypeRange(0, 0)))


@pytest.mark.parametrize("seed", [0, 1, -1, -(1 << 63), (1 << 63) - 1])
def test_seed_origin_and_reproducible_new_preparation(seed):
    left = prepare_random_input(config(seed)); right = prepare_random_input(config(seed))
    assert left.rng_seed_decimal == str(encode_seed(seed))
    assert left.rng.getstate() == random.Random(encode_seed(seed)).getstate()
    assert left.rng is not right.rng and left.samplers is not right.samplers
    for item in fields(left.samplers):
        assert getattr(left.samplers, item.name) is not getattr(right.samplers, item.name)
    assert left.snapshot() == right.snapshot()
    assert left.samplers.workload.sample(left.rng) == right.samplers.workload.sample(right.rng)
    assert left.snapshot().fingerprint == right.snapshot().fingerprint


def test_signed_seed_encoding_prevents_abs_seed_collision():
    positive = prepare_random_input(config(1)); negative = prepare_random_input(config(-1))
    assert positive.rng.getstate() != negative.rng.getstate()


def test_one_rng_created_after_catalog_and_shared_by_consumers(monkeypatch):
    original = random.Random
    constructed = []
    class CountedRandom(original):
        def __init__(self, seed):
            constructed.append(seed)
            super().__init__(seed)
    monkeypatch.setattr(random, "Random", CountedRandom)
    prepared = prepare_random_input(config(-1))
    assert constructed == [(1 << 64) - 1]
    # Future device/environment consumers use the same prepared stream and roles.
    consumers = [prepared, prepared]
    assert consumers[0].rng is consumers[1].rng
    assert consumers[0].samplers.weight is consumers[1].samplers.weight
    expected = original(encode_seed(-1))
    for consumer in consumers:
        u = expected.random()
        assert consumer.samplers.weight.sample(consumer.rng) == (4 if u < .2 else 2 if u < .8 else 1)
    assert prepared.rng.getstate() == expected.getstate()


def test_snapshot_and_restore_have_no_draws_and_do_not_change_seed_or_catalog():
    prepared = prepare_random_input(config(-1))
    snapshot = prepared.snapshot()
    assert snapshot.state_version == 3 and snapshot.seed_encoding == "signed64-bits-v1"
    assert prepared.snapshot() == snapshot
    first = [prepared.samplers.workload.sample(prepared.rng) for _ in range(3)]
    prepared.restore_rng(snapshot)
    assert [prepared.samplers.workload.sample(prepared.rng) for _ in range(3)] == first
    assert prepared.public_seed == -1
    with pytest.raises(FrozenInstanceError): prepared.public_seed = 3
    current = prepared.snapshot()
    for bad in (replace(snapshot, python_version="different"),
                replace(snapshot, native_state=(99, snapshot.native_state[1], None)),
                replace(snapshot, native_state=(3, (), None))):
        with pytest.raises(InputError): prepared.restore_rng(bad)
        assert prepared.snapshot() == current


def test_prepare_requires_expanded_dynamic_config():
    cfg = config()
    with pytest.raises(InputError): prepare_random_input({})
    batch = replace(cfg, repeat=RepeatConfig(2, "fresh_same_seed"))
    with pytest.raises(InputError): prepare_random_input(batch)
    listed = replace(cfg, source=replace(cfg.source, seed=None), repeat=RepeatConfig(1, "fresh_seed_list", [-1]))
    with pytest.raises(InputError): prepare_random_input(listed)
    assert prepare_random_input(listed.single_run()).public_seed == -1

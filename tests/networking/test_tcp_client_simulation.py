"""Validate artificial network simulation helpers in the TCP client."""

from networking.tcp_client import _NetworkSimulation


def test_network_simulation_delay_sampling_with_spike(
    monkeypatch,
) -> None:
    """Assert delay sampling combines jitter and spike components."""
    simulation = _NetworkSimulation(
        base_delay_s=0.05,
        delay_jitter_s=0.02,
        delay_spike_prob=0.5,
        delay_spike_s=0.1,
        packet_loss_prob=0.0,
    )

    random_values = iter([0.2])  # spike condition: 0.2 < 0.5 -> spike applied
    monkeypatch.setattr(
        "networking.tcp_client.random.uniform",
        lambda a, b: 0.01,
    )
    monkeypatch.setattr(
        "networking.tcp_client.random.random",
        lambda: next(random_values),
    )

    assert simulation.sample_delay_s() == 0.16


def test_network_simulation_packet_loss_probability(
    monkeypatch,
) -> None:
    """Assert packet loss decision follows configured probability."""
    simulation = _NetworkSimulation(
        base_delay_s=0.0,
        delay_jitter_s=0.0,
        delay_spike_prob=0.0,
        delay_spike_s=0.0,
        packet_loss_prob=0.25,
    )

    random_values = iter([0.1, 0.8])
    monkeypatch.setattr(
        "networking.tcp_client.random.random",
        lambda: next(random_values),
    )

    assert simulation.should_drop_message() is True
    assert simulation.should_drop_message() is False

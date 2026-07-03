from proxy_auth import ip_in_networks, parse_trusted_networks


def test_parse_skips_invalid_and_blank():
    nets = parse_trusted_networks("10.0.0.0/8, , not-an-ip, 192.168.1.5")
    assert len(nets) == 2


def test_bare_ip_matches_exactly():
    nets = parse_trusted_networks("192.168.1.5")
    assert ip_in_networks("192.168.1.5", nets)
    assert not ip_in_networks("192.168.1.6", nets)


def test_cidr_contains():
    nets = parse_trusted_networks("10.0.0.0/8")
    assert ip_in_networks("10.4.5.6", nets)
    assert not ip_in_networks("11.0.0.1", nets)


def test_none_and_invalid_peer_are_false():
    nets = parse_trusted_networks("10.0.0.0/8")
    assert not ip_in_networks(None, nets)
    assert not ip_in_networks("", nets)
    assert not ip_in_networks("garbage", nets)


def test_empty_allowlist_never_matches():
    assert not ip_in_networks("10.0.0.1", parse_trusted_networks(""))


def test_mixed_ipv4_ipv6_no_crash():
    nets = parse_trusted_networks("::1/128, 10.0.0.0/8")
    assert ip_in_networks("10.0.0.9", nets)
    assert ip_in_networks("::1", nets)
    assert not ip_in_networks("10.0.0.9", parse_trusted_networks("::1/128"))

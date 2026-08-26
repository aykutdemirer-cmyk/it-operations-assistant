import ipaddress


class InvalidCIDRError(ValueError):
    pass


def parse_ipv4_cidr(cidr: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(cidr, strict=False)
    except ValueError as exc:
        raise InvalidCIDRError(f"Geçersiz CIDR: {cidr}") from exc

    if not isinstance(network, ipaddress.IPv4Network):
        raise InvalidCIDRError("Yalnızca IPv4 CIDR desteklenir")

    return network


def list_host_ips(network: ipaddress.IPv4Network) -> list[str]:
    return [str(ip) for ip in network.hosts()]

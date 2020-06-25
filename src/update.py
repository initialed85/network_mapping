import json
import pprint
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from typing import NamedTuple, List, Set, Dict, Tuple

from netmiko import ConnectHandler


class Output(NamedTuple):
    host: str
    interface_mac_addresses: str
    mac_address_table: str


class MACAddressTableEntry(NamedTuple):
    mac: str
    port: str


class PartialLink(NamedTuple):
    source_host: str
    source_port: str
    destination_host: str


class Link(NamedTuple):
    source_host: str
    source_port: str
    destination_host: str
    destination_port: str


def _get_output_from_cisco_ios_device(
    host: str, username: str, password: str
) -> Output:
    connection = ConnectHandler(
        device_type="cisco_ios", host=host, username=username, password=password,
    )

    # disable pagination
    connection.send_command("term len 0")

    return Output(
        host=host,
        interface_mac_addresses=connection.send_command(
            "show interfaces | i , address is"
        ),
        mac_address_table=connection.send_command("show mac address-table | i DYNAMIC"),
    )


def _get_outputs_from_cisco_ios_devices(
    hosts: List[str], username: str, password: str, max_workers: int = 10
):
    # use this to hit up to max_workers devices concurrently
    executor = ThreadPoolExecutor(max_workers=max_workers)

    futures: List[Future] = []
    for host in hosts:
        futures += [
            executor.submit(
                fn=_get_output_from_cisco_ios_device,
                host=host,
                username=username,
                password=password,
            )
        ]

    outputs: List[Output] = []
    for future in as_completed(futures):
        try:
            output: Output = future.result()
        except Exception as e:
            print(
                f"caught {repr(e)} trying to scrape device; skipping- traceback follows:\n{traceback.format_exc()}"
            )
            continue

        outputs += [output]

    return outputs


def _reformat_mac_address(mac: str):
    mac = mac.replace(":", "").replace(".", "")
    if len(mac) != 12:
        raise ValueError(f"{repr(mac)} doesn't seem to be a mac")

    return ":".join([mac[i : i + 2] for i in range(0, 12, 2)])


def _parse_mac_address_table_from_output(output: Output) -> List[MACAddressTableEntry]:
    mac_address_table_entries: List[MACAddressTableEntry] = []
    for line in output.mac_address_table.split("\n"):
        # e.g. [9, "001d.4543.b973", "DYNAMIC", "Gi0/6"]
        parts = line.split()

        if len(parts) != 4:
            print(f"unexpected parts {repr(parts)}; skipping")
            continue

        mac = _reformat_mac_address(parts[1])

        port = parts[3]

        mac_address_table_entries += [MACAddressTableEntry(mac=mac, port=port)]

    return mac_address_table_entries


def _parse_interface_mac_addresses_from_output(output: Output) -> Set[str]:
    macs: List[str] = []
    for line in output.interface_mac_addresses.split("\n"):
        try:
            mac = line.split(", address is ")[1].split()[0]
        except Exception as e:
            print(f"failed to find mac in {repr(line)} because {repr(e)}; skipping")
            continue

        mac = _reformat_mac_address(mac)

        # reported by an unconfigured EtherChannel
        if mac == "00:00:00:00:00:00":
            continue

        macs += [mac]

    return set(macs)


def _get_links_from_outputs(outputs: List[Output]) -> List[Link]:
    interface_mac_addresses_by_host: Dict[str, Set[str]] = {
        x.host: _parse_interface_mac_addresses_from_output(output=x) for x in outputs
    }

    host_by_interface_mac: Dict[str, str] = {}
    for host, interface_mac_addresses in interface_mac_addresses_by_host.items():
        for interface_mac_address in interface_mac_addresses:
            host_by_interface_mac[interface_mac_address] = host

    mac_address_table_entries_by_host: Dict[str, List[MACAddressTableEntry]] = {
        x.host: _parse_mac_address_table_from_output(output=x) for x in outputs
    }

    partial_link_by_source_and_destination: Dict[Tuple[str, str], PartialLink] = {}
    for host, mac_address_table_entries in mac_address_table_entries_by_host.items():
        for mac_address_table_entry in mac_address_table_entries:
            other_host = host_by_interface_mac.get(mac_address_table_entry.mac)
            if other_host is None:
                continue

            partial_link = PartialLink(
                source_host=host,
                source_port=mac_address_table_entry.port,
                destination_host=other_host,
            )

            partial_link_by_source_and_destination[(host, other_host)] = partial_link

    links: List[Link] = []
    for (
        (source, destination),
        partial_link,
    ) in partial_link_by_source_and_destination.items():
        opposite_partial_link = partial_link_by_source_and_destination.get(
            (destination, source)
        )
        if opposite_partial_link is None:
            continue

        link = Link(
            source_host=partial_link.source_host,
            source_port=partial_link.source_port,
            destination_host=opposite_partial_link.source_host,
            destination_port=opposite_partial_link.source_port,
        )

        opposite_link = Link(
            source_host=link.destination_host,
            source_port=link.destination_port,
            destination_host=link.source_host,
            destination_port=link.source_port,
        )

        if link in links or opposite_link in links:
            continue

        links += [link]

    return links


def get_links_from_cisco_ios_devices(
    hosts: List[str], username: str, password: str, max_workers: int = 10
) -> str:
    outputs = _get_outputs_from_cisco_ios_devices(
        hosts=hosts, username=username, password=password, max_workers=max_workers
    )
    print(f"outputs = {pprint.pformat(outputs)}")

    links = _get_links_from_outputs(outputs=outputs)
    print(f"links = {pprint.pformat(links)}")

    host_by_host_id = {i: outputs[i].host for i in range(len(outputs))}

    host_id_by_host = {v: k for k, v in host_by_host_id.items()}

    nodes = [
        {"id": host_id, "label": host} for host_id, host in host_by_host_id.items()
    ]

    edges = [
        {
            "from": host_id_by_host[link.source_host],
            "to": host_id_by_host[link.destination_host],
            "label": f"{link.source_port} - {link.destination_port}",
        }
        for link in links
    ]

    return json.dumps({"nodes": nodes, "edges": edges}, sort_keys=True, indent=4)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--username", type=str, required=True)
    parser.add_argument("--password", type=str, required=True)
    parser.add_argument("--host", type=str, action="append")

    args = parser.parse_args()

    data = get_links_from_cisco_ios_devices(
        hosts=args.host, username=args.username, password=args.password
    )

    with open("/usr/share/nginx/html/data.json", "w") as f:
        f.write(data)

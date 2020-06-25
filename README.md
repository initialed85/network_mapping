# network_mapping

This repo contains a pretty naive network mapping example as a demo.

## How do I use it?

### Prerequisites

- [Docker](https://docs.docker.com/engine/install/)
- Some Cisco switches w/ SSH enabled

### Steps

- Create the container
    - `docker run --rm -it --name network_mapping -p 8080:80`
- Open a browser window to  http://localhost:8080 and you should be able to see a blank page
- Update the data in the container (specify as many hosts as you like)
    - `docker exec -it network_mapping ./update.sh --username some_user --password some_pass --host host1.org --host host2.org --host host3.org --host host4.org`
- Back in the browser window, you should now see your network graph 

## How does it work?

- Nginx web server in a Docker container
    - Hosting an `index.html` with a [vis.js](https://visjs.org/) implementation
    - Reads from a static `data.json` file
- Externally invoking `update.sh` calls `update.py` (Python3)
    - Uses [Netmiko](https://pynet.twb-tech.com/blog/automation/netmiko.html) to interrogate the Cisco IOS devices via SSH
    - Gets the output from `show interfaces` and `show mac address-table` 
    - Does a bunch of parsing and mapping of data
    - Generates and replaces the contents of `data.json`

## How could I extend it?

- add support for interrogating more devices for the MACs of their interfaces and the MACs they can see out those interfaces
- add functions to parse that data as required (minimal parsing required if SNMP)
- feed that in toward the top of `update.py::_get_links_from_outputs(outputs: List[Output]) -> List[Link]` as additional input

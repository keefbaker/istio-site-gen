"""
Generates istio manifests for allowing sites through the
istio egress gateway.

Run this with the config filename as an argument.

Generated manifests will be in the output_manifests folder
"""
import argparse
import os
import yaml


def parse_args():
    """argument parser"""
    parser = argparse.ArgumentParser()
    parser.add_argument("filename", help="which file contains your yaml config")
    return parser.parse_args()


def get_initial_data(filename, sitename):
    """
    Gets the template to build from, and also returns
    a name that can be used in the manifest for the site
    """
    with open(
        f"{os.path.dirname(os.path.realpath(__file__))}/templates/{filename}",
    encoding="UTF-8") as stream:
        data = yaml.safe_load(stream)
    easyname = sitename["site"].replace("*.", "").replace(".", "-").replace("*", "")
    return data, easyname


def get_config():
    """gets the filename argument and opens the config"""
    args = parse_args()
    with open(args.filename, encoding="UTF-8") as yamlfile:
        return yaml.safe_load(yamlfile)


def generate_gateway(site):
    """
    Creates the gateway manifest
    """
    template, easyname = get_initial_data("gateway.yaml", site)
    if not site.get("ports"):
        site["ports"] = [{"port": 80, "proto": "HTTP"}, {"port": 443, "proto": "TLS"}]
    template["metadata"]["name"] = f"{easyname}-gateway"
    for port in site["ports"]:
        portdata = {
            "port": {
                "number": port["port"],
                "name": f"{easyname}-{port['port']}",
                "protocol": port["proto"],
            },
            "hosts": [site["site"]],
        }
        if port["proto"] == "TLS":
            portdata["tls"] = {"mode": "PASSTHROUGH"}
        template["spec"]["servers"].append(portdata)
    return template


def generate_destination_rule(site, gateway):
    """
    creates the destination rule manifest
    """
    template, easyname = get_initial_data("destrule.yaml", site)
    template["metadata"]["name"] = f"egress-for-{easyname}"
    template["spec"]["host"] = gateway
    template["spec"]["subsets"][0]["name"] = easyname
    return template

def generate_service(site):
    """
    creates the service entry
    """
    template, easyname = get_initial_data("service.yaml", site)
    template["metadata"]["name"] = easyname
    template["spec"]["hosts"].append(site["site"])
    if not site.get("ports"):
        site["ports"] = [{"port": 80, "proto": "HTTP"}, {"port": 443, "proto": "TLS"}]
    for port in site["ports"]:
        template["spec"]["ports"].append(
            {
                "number": port["port"],
                "name": f"{port['proto'].lower()}-{port['port']}",
                "protocol": port["proto"]
            }
        )
    return template

def generate_virtual_service(site, gateway):
    """
    creates the virtual service
    """
    template, easyname = get_initial_data("virtual_service.yaml", site)
    template["metadata"]["name"] = f"direct-{easyname}"
    template["spec"]["hosts"] = [site["site"]]
    template["spec"]["gateways"].append(f"{easyname}-gateway")
    http = []
    tls = []
    if not site.get("ports"):
        site["ports"] = [{"port": 80, "proto": "HTTP"}, {"port": 443, "proto": "TLS"}]
    for port in site["ports"]:
        meshdata = [
            {
                "match": [{"gateways": ["mesh"], "port": port["port"]}],
                "route": [
                    {
                        "destination": {
                            "host": gateway,
                            "subset": easyname,
                            "port": {"number": port["port"]},
                        },
                        "weight": 100,
                    }
                ],
            },
            {
                "match": [{"gateways": [f"{easyname}-gateway"], "port": port["port"]}],
                "route": [
                    {
                        "destination": {
                            "host": site["site"],
                            "port": {"number": port["port"]},
                        }
                    }
                ],
            },
        ]
        if port["proto"] == "TLS":
            for item in meshdata:
                item["match"][0]["sniHosts"] = [site["site"]]
            tls += meshdata
        else:
            http += meshdata
    if http:
        template["spec"]["http"] = http
    if tls:
        template["spec"]["tls"] = tls
    return template


def main():
    """
    Primary entrypoint
    * loads the config
    * generates the manifest data
    * writes that data out
    """
    config = get_config()
    if not config.get("istio_gateway"):
        config["istio_gateway"] = "istio-egressgateway.istio-system.svc.cluster.local"
    for site in config["sites"]:
        name = site['site'].replace('*.', '').replace('.', '-').replace('*', '')
        filename = (
            f"output_manifests/{name}.yaml"
        )
        print(f">Processing {site['site']} to {filename}")
        destrule = generate_destination_rule(site, config["istio_gateway"])
        gateway = generate_gateway(site)
        service = generate_service(site)
        virtual_service = generate_virtual_service(site, config["istio_gateway"])
        with open(filename, "w", encoding="UTF-8") as output_file:
            output_file.write(
                yaml.dump_all(
                    [destrule, gateway, service, virtual_service], default_flow_style=False
                )
            )


if __name__ == "__main__":
    main()

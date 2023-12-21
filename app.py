#!/usr/bin/env python3
import configparser
from PythonPSI.api import PSI
from pyzabbix import ZabbixAPI
from zappix.sender import Sender
import signal

def handler(signum, frame):
    raise TimeoutError()

def get_config(conf_file):
    try:
        config = configparser.ConfigParser()
        config.read(conf_file)
        return config
    except Exception as e:
        print(f"Get config error : {e}")

def get_websites(config):
    try:
        with open(config['WEBSITES']['WEBSITES_LIST'], 'r') as f:
            sites = f.read().splitlines()
        return sites, len(sites)
    except Exception as e:
        print(f"Get websites list error : {e}")
    

def get_websites_psi(website, category, strategy, timeout=45):
    def set_timeout():
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(timeout)

    try:
        set_timeout()
        website = f"https://{website}"
        data = PSI(website, strategy=strategy, category=category)
        if category == "performance":
            results = {
                "score": int(data["lighthouseResult"]["categories"][category]["score"] * 100),
                "First_Contentful_Paint": data["lighthouseResult"]["audits"]["metrics"]["details"]["items"][0]["observedFirstContentfulPaint"],
                "Total_BlockingTime": data["lighthouseResult"]["audits"]["metrics"]["details"]["items"][0]["totalBlockingTime"],
                "Speed_Index": data["lighthouseResult"]["audits"]["metrics"]["details"]["items"][0]["speedIndex"],
                "Largest_Contentful_Paint": data["lighthouseResult"]["audits"]["metrics"]["details"]["items"][0]["largestContentfulPaint"],
                "Cumulative_Layout_Shift": round(data["lighthouseResult"]["audits"]["metrics"]["details"]["items"][0]["cumulativeLayoutShiftMainFrame"], 2)
            }
        else:
            results = {
                "score": int(data["lighthouseResult"]["categories"][category]["score"] * 100)
            }

        signal.alarm(0)
        return results

    except TimeoutError:
        print(f"Operation timed out for {website}")

    except Exception as e:
        print(f"Get Pagespeed for {website} error : {e}")
    finally:
        signal.alarm(0)

def send_to_zabbix(hostname, website, category, strategy, results):
    try:
        sender = Sender(f"{config['ZABBIX']['ZABBIX_SERVER']}")
        host = zapi.host.get(filter={"host": hostname})
        if not host:
            host_id = zapi.host.create(
                host=hostname,
                interfaces=[{
                    "type": 1,
                    "main": 1,
                    "useip": 1,
                    "ip": "192.168.1.1",
                    "dns": "",
                    "port": "10050"
                }],
                groups=[{"groupid": "19"}]
            )['hostids'][0]
        else:
            host_id = host[0]['hostid']
        if category == "performance":
            for key, value in results.items():
                item_name = f"{website} - {strategy} - {category}_{key}"
                item = zapi.item.get(filter={"name": item_name, "hostid": host_id})
                if not item:
                    zapi.item.create(
                        name=item_name,
                        key_=f'{website}.{strategy}.{category}.{key}', 
                        hostid=host_id,
                        type=2,
                        value_type=0,
                        delay='30s'
                    )
                zabbix_result = sender.send_value(host=hostname, key=f'{website}.{strategy}.{category}.{key}', value=value)
        else:
            item_name = f"{website} - {strategy} - {category}_score"
            item = zapi.item.get(filter={"name": item_name, "hostid": host_id})
            if not item:
                zapi.item.create(
                    name=item_name,
                    key_=f'{website}.{strategy}.{category}.score', 
                    hostid=host_id,
                    type=2,
                    value_type=3,
                    delay='30s'
                )
            zabbix_result = sender.send_value(host=hostname, key=f'{website}.{strategy}.{category}.score', value=results['score'])

    except Exception as e:
        print(f"Zabbix error : {e}")


# Main
if __name__ == "__main__":
    config = get_config('./settings.conf')
    websites, nbt_websites = get_websites(config)
    categories = [item.strip() for item in config['PAGESPEED']['CATEGORIES'].split(',')]
    strategies = [item.strip() for item in config['PAGESPEED']['strategies'].split(',')]
    try:
        zapi = ZabbixAPI(f"https://{config['ZABBIX']['ZABBIX_SERVER']}/api_jsonrpc.php?")
        zapi.login(config['ZABBIX']['ZABBIX_USERNAME'], config['ZABBIX']['ZABBIX_PASSWORD'])
    except Exception as e:
        print(f"Zabbix connexion error : {e}")
    nb_websites = 0
    for website in websites:
        nb_websites += 1
        results_list = []
        print(f"\n({nb_websites}/{nbt_websites}) {website}")
        for strategy in strategies:
            print(f"- {strategy} -")
            for category in categories:
                results = get_websites_psi(website, category, strategy,timeout=45)
                if results is not None:
                    score = results.get('score', 'No score available')
                    print(f"{category} : {score}")
                    if 'score' in results:
                        results_list.append((config['ZABBIX']['ZABBIX_HOST'], website, category, strategy, results))
                    else:
                        print(f"Data incomplete for {website}, {category}, {strategy}")
                else:
                    print(f"{category} : No data (timeout or error)")
        for result in results_list:
            send_to_zabbix(*result)

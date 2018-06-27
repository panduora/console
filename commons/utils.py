# -*- coding: utf-8

import json
import etcd3 as etcd
from retrying import retry
from etcd3.exceptions import Etcd3Exception as EtcdException


def get_etcd_client(etcd_authority):
    etcd_host_and_port = etcd_authority.split(":")
    if len(etcd_host_and_port) == 2:
        return etcd.client(host=etcd_host_and_port[0], port=int(etcd_host_and_port[1]))
    elif len(etcd_host_and_port) == 1:
        return etcd.client(host=etcd_host_and_port[0], port=4001)
    else:
        raise Exception("invalid ETCD_AUTHORITY : %s" % etcd_authority)


def retry_if_etcd_error(exception):
    return isinstance(exception, EtcdException)


@retry(wait_fixed=200, stop_max_attempt_number=3, retry_on_exception=retry_if_etcd_error)
def read_from_etcd(key, etcd_authority):
    client = get_etcd_client(etcd_authority)
    value, _ = client.get(key)
    return value


@retry(wait_fixed=200, stop_max_attempt_number=3, retry_on_exception=retry_if_etcd_error)
def keys_from_etcd(prefix, etcd_authority):
    client = get_etcd_client(etcd_authority)
    return client.get_prefix(prefix)


@retry(wait_fixed=200, stop_max_attempt_number=3, retry_on_exception=retry_if_etcd_error)
def set_value_to_etcd(key, value, etcd_authority):
    client = get_etcd_client(etcd_authority)
    return client.put(key, value)


@retry(wait_fixed=200, stop_max_attempt_number=3, retry_on_exception=retry_if_etcd_error)
def delete_from_etcd(key, etcd_authority, recursive=False, dir=False):
    client = get_etcd_client(etcd_authority)
    return client.delete(key, recursive=recursive, dir=dir)


def get_etcd_value(key, etcd_authority, default=None):
    return read_from_etcd(key, etcd_authority) or default


def get_extra_domains(key, etcd_authority):
    v = get_etcd_value(key, etcd_authority, default='[]')
    return json.loads(v)


def get_system_volumes(key, etcd_authority):
    system_volumes = {}
    try:
        volume_keys = keys_from_etcd(key, etcd_authority)
        for volume_key, _ in volume_keys:
            appname = volume_key[len(key) + 1:]
            v = get_etcd_value(volume_key, etcd_authority, default="")
            sys_vol = [] if v == "" else v.split(";")
            system_volumes[appname] = sys_vol
        return system_volumes
    except Exception:
        return {}

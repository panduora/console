# -*- coding: utf-8

import requests
import tarfile
import yaml
import json
import subprocess
import re
from retrying import retry
from time import gmtime, strftime
from docker import Client
from docker.utils import create_ipam_config, create_ipam_pool
from cStringIO import StringIO
from commons.miscs import NoAvailableImages
import commons.utils
from commons.settings import (PRIVATE_REGISTRY, DOCKER_BASE_URL, DEBUG,
                              ETCD_AUTHORITY, SYSTEM_VOLUMES,
                              DOMAIN, EXTRA_DOMAINS)
from log import logger


def read_from_etcd(key):
    return commons.utils.read_from_etcd(key, ETCD_AUTHORITY)


def keys_from_etcd(key):
    return commons.utils.keys_from_etcd(key, ETCD_AUTHORITY)


def set_value_to_etcd(key, value):
    return commons.utils.set_value_to_etcd(key, value, ETCD_AUTHORITY)


def delete_from_etcd(key, recursive=False, dir=False):
    return commons.utils.delete_from_etcd(key, ETCD_AUTHORITY, recursive=recursive, dir=dir)


def get_domains():
    return [DOMAIN] + EXTRA_DOMAINS


VALID_TAG_PATERN = re.compile(r"^(meta)-(?P<meta_version>\S+-\S+)$")


def get_meta_version_from_tag(tag):
    if tag is None:
        return None
    x = VALID_TAG_PATERN.match(tag)
    if x:
        return x.group('meta_version')
    else:
        return None


def get_docker_client(docker_base_url):
    # FIXME: `docker network ls` takes too long, increase timeout temporarily
    return Client(base_url=docker_base_url, timeout=100)


def normalize_meta_version(meta_version):
    return meta_version.replace("meta-", "").replace("build-", "").replace("release-", "")


def gen_image_name(app, meta_version, phase='meta', registry=None):
    if not registry:
        registry = PRIVATE_REGISTRY
    return "%s/%s:%s-%s" % (registry, app, phase, meta_version)


def _is_registry_auth_open(registry=None):
    if not registry:
        registry = PRIVATE_REGISTRY
    url = "http://%s/v2/" % registry
    r = requests.get(url)
    if r.status_code == 401:
        return True
    else:
        return False


def _get_registry_access_header(app, registry):
    if _is_registry_auth_open(registry):
        from authorize.models import Authorize

        jwt = Authorize.get_jwt_with_appname(app)
        header = {'Authorization': 'Bearer %s' % jwt}
    else:
        header = ''
    return header


def search_images_from_registry(app, registry=None):
    if not registry:
        registry = PRIVATE_REGISTRY

    url = "http://%s/v2/%s/tags/list" % (registry, app)
    header = _get_registry_access_header(app, registry)
    r = requests.get(url, headers=header)
    if r.status_code != 200:
        raise NoAvailableImages("no images here: %s" % url)
    else:
        return r.json()


def get_meta_from_registry(app, meta_version, registry=None):
    logger.debug("ready get meta version %s for app %s from registry" %
                 (meta_version, app))
    meta_version = normalize_meta_version(meta_version)
    if not registry:
        registry = PRIVATE_REGISTRY
    try:
        y = None
        c = None
        cli = None
        cli = get_docker_client(DOCKER_BASE_URL)
        # TODO check if the image already exits
        cli.pull(
            repository="%s/%s" % (registry, app),
            tag="meta-%s" % (meta_version, ),
            insecure_registry=True
        )
        image = "%s/%s:meta-%s" % (registry, app, meta_version)
        command = '/bin/sleep 0.1'
        c = cli.create_container(image=image, command=command)
        r = cli.copy(container=c.get('Id'), resource='/lain.yaml')
        tar = tarfile.open(fileobj=StringIO(r.data))
        f = tar.extractfile('lain.yaml')
        y = yaml.safe_load(f.read())
    except Exception, e:
        logger.error("fail get yaml from %s %s: %s" % (app, meta_version, e))
        raise Exception("fail get yaml from %s %s: %s" %
                        (app, meta_version, e))
    finally:
        if cli and isinstance(c, dict) and c.get('Id'):
            cli.remove_container(container=c.get('Id'), v=True)
    return y


def shell(cmd):
    retcode = 0
    output = None
    try:
        output = subprocess.check_output(
            cmd, stderr=subprocess.STDOUT, shell=True)
    except:
        retcode = 1
    finally:
        return (retcode, output)


def docker_network_exists(name):
    cli = get_docker_client(DOCKER_BASE_URL)
    filter_name = '^%s$' % name
    if len(cli.networks(names=[filter_name])) == 0:
        return False
    else:
        return True


def get_system_volumes_from_etcd(appname):
    return SYSTEM_VOLUMES.get(appname, [])


def get_current_time():
    return strftime("%Y-%m-%d %H:%M:%S", gmtime())


def convert_time_from_deployd(d_time):
    c_times = d_time.split("T")
    if len(c_times) <= 1:
        return d_time
    else:
        return "%s %s" % (c_times[0], c_times[1].split('.')[0])

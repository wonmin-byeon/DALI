#!/usr/bin/env python
from __future__ import print_function, division
import argparse
import sys
# use packaging from PIP as it is always present on system we are testing on
from pip._vendor.packaging.version import parse
import urllib.parse
try:
    import pip._internal.utils.compatibility_tags as p
except ImportError:
    try:
        import pip._internal.pep425tags as p
    except ImportError:
        import pip.pep425tags as p
try:
    # For Python 3.0 and later
    from urllib.request import urlopen, HTTPError, Request
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import urlopen, HTTPError, Request

PYTHON_VERSION = ".".join([str(x) for x in sys.version_info[0:2]])

class PckgVer():
    """Class that holds a version string accompanied with maximum and minimum python version that
        this version should support. If python falls beyond version bounds it evaluates to the empty string

        Parameters
        ----------
        `ver`: str
            Version that is housed by object of this class
        `python_max_ver` : str, optional, default = None
            Maximum python version supported by this package. If empty there is no upper bound
        `python_min_ver`: str, optional, default = None
            Mimimum python version supported by this package. If empty there is no lower bound
    """
    def __init__(self, ver, python_min_ver=None, python_max_ver=None):
        self.ver = ver
        self.python_min_ver = python_min_ver
        self.python_max_ver = python_max_ver

    def __bool__(self):
        return (not self.python_min_ver or parse(PYTHON_VERSION) >= parse(self.python_min_ver)) and \
           (not self.python_max_ver or parse(PYTHON_VERSION) <= parse(self.python_max_ver))

    def __repr__(self):
        if self:
            return self.ver
        else:
            return ""

class BasePackage():
    """Class describing basic methods that package should provide

        Parameters
        ----------
        `key`: str
            Name this package should be queried for
        `versions`: str or PckgVer class object
            List of versions this package is available for
        `name`: str, , optional, default = None
            Name of this package used during installation. If empty it is the same as the key
    """
    def __init__(self, key, versions, name=None):
        self.key = key
        if not name:
            name = key
        self.name = name
        self.versions = versions

    def clamp_index(self, idx, cuda_version=None):
        """Clamps index to range 0 - num_of_packages - 1

            Parameters
            ----------
            `key`: idx: int
                Index to clamp
            `cuda_version`: str, optional, default = None
                Cuda version used for a given index
        """
        if idx < 0 or idx >= self.get_num_of_version(cuda_version):
            idx = 0
        return idx

    def get_name(self, cuda_version=None):
        """Retrives package name.

            Parameters
            ----------
            `cuda_version`: str, optional, default = None
                Cuda version used for this query
        """
        raise NotImplementedError

    def filter_versions(self, versions):
        """Retrieves only compatible versions of this package from provided `versions` list

            Parameters
            ----------
            `versions`: list
                List of versions to be checked. All versions that evaluate to True are returned
        """
        # convert PckgVer to string
        return [str(v) for v in versions if v]

    def get_version(self, idx, cuda_version=None):
        """Get versions at a given index, compatible with provided cuda_version

            Parameters
            ----------
            `idx`: int
                Index of version to retrive. If index is beyond 0-num_of_versions-1 range
                it is clamped to it
            `cuda_version`: str, optional, default = None
                Cuda version used for this query
        """
        idx = self.clamp_index(idx, cuda_version)
        return self.get_all_versions(cuda_version)[idx]

    def get_all_versions(self, cuda_version=None):
        """Get all versions compatible with provided cuda_version

            Parameters
            ----------
            `cuda_version`: str, optional, default = None
                Cuda version used for this query
        """
        raise NotImplementedError

    def get_num_of_version(self, cuda_version=None):
        """Obtains the number of available versions for given cuda_version

            Parameters
            ----------
            `cuda_version`: str, optional, default = None
                Cuda version used for this query
        """
        return len(self.get_all_versions(cuda_version))

    def get_install_string(self, idx, cuda_version=None):
        """Obtains installation string that pip should accept for version at
        a given index with a given cuda_version

            Parameters
            ----------
            `idx`: int
                Index of version to retrive. If index is beyond 0-num_ov_versions-1 range
                it is clamped to it
            `cuda_version`: str, optional, default = None
                Cuda version used for this query
        """
        return "{name}=={version}".format(name=self.get_name(cuda_version), version=self.get_version(idx, cuda_version))

    def get_all_install_strings(self, cuda_version=None):
        """Gets all installation string that pip should accept for a given
        cuda version. Providing all of them to pip won't work, but each of
        them should be a valid pip argument

            Parameters
            ----------
            `cuda_version`: str, optional, default = None
                Cuda version used for this query
        """
        ret = []
        for i in range(self.get_num_of_version(cuda_version)):
            ret.append(self.get_install_string(i, cuda_version))
        return " ".join(ret)

class PlainPackage(BasePackage):
    """Class describing a simple package with a key/name and a list of versions.
        Cuda version is irrelevant for this package

        Parameters
        ----------
        `key`: str
            Name this package should be queried for
        `versions`: str or PckgVer class object
            List of versions this package is available for
        `name`: str, , optional, default = None
            Name of this package used during installation. If empty it is the same as the key
    """
    def __init__(self, key, versions, name=None):
        super(PlainPackage, self).__init__(key, versions, name)

    def get_name(self, cuda_version=None):
        return self.name

    def get_all_versions(self, cuda_version=None):
        return self.filter_versions(self.versions)

class CudaPackage(BasePackage):
    """Class describing a cuda package with a key/name and a dictionary where the key
        is a cuda version and value is the list of versions supported.

        Parameters
        ----------
        `key`: str
            Name this package should be queried for
        `versions`: str or PckgVer class object
            Dictionary, where the key is a cuda version and vale, is the list of versions supported
        `name`: str, , optional, default = None
            Name of this package used during installation. If empty it is the same as the key.
            If it includes `{cuda_v}` it is replaced by the cuda_version when queried
    """
    def __init__(self, key, versions, name=None):
        super(CudaPackage, self).__init__(key, versions, name)
        if not isinstance(versions, dict):
            raise TypeError("versions argument should by dict type [cuda_version : list_of_versions")

    def get_name(self, cuda_version):
        cuda_version = self.max_cuda_version(cuda_version)
        return self.name.format(cuda_v=cuda_version)

    def get_all_versions(self, cuda_version):
        cuda_version = self.max_cuda_version(cuda_version)
        return self.filter_versions(self.versions[cuda_version])

    def max_cuda_version(self, cuda_version):
        """Gets a compatible, available cuda version to one asked for.
            If there is no cuda version in the version list that matches the one provided,
            the cuda version that is not higher is used 10.2 -> 10, 9.2 -> 9

            Parameters
            ----------
            `cuda_version`: str
                Cuda version used for this query
        """
        max_cuda = None
        for ver in sorted(self.versions.keys(), key=int):
            if int(ver) <= int(cuda_version):
                max_cuda = ver
        return max_cuda

class CudaHttpPackage(CudaPackage):
    """Class describing a cuda package with a key/name and a dictionary where the key
        is a cuda version and value is the list of directly accessible http links

        When it asked for a package version it checks compatible platform tags and provides
        a download link to a compatible package

        Parameters
        ----------
        `key`: str
            Name this package should be queried for
        `versions`: str or PckgVer class object
            Dictionary, where the key is a cuda version and vale, is the list
            of directly accessible http links. `{platform}` inside the link is replaced by the
            compatible platform tag provided by pip
        `name`: str, , optional, default = None
            Name of this package used during installation. If empty it is the same as the key.
            If it includes `{cuda_v}` it is replaced by the cuda_version when queried
    """
    def __init__(self, key, versions, name=None):
        super(CudaHttpPackage, self).__init__(key, versions, name)

    def get_all_versions(self, cuda_version):
        cuda_version = self.max_cuda_version(cuda_version)
        ret = []
        for v in self.versions[cuda_version]:
            vers = self.get_pyvers_name(v, cuda_version)
            if vers != "":
                ret.append(vers)
        return ret

    def get_install_string(self, idx, cuda_version=None):
        return "{version}".format(version=self.get_version(idx, cuda_version))

    def test_request(self, url):
        """Checks if a provided url is available

            Parameters
            ----------
            `url`: str
                Package url to be tested.
        """
        url = url.split("://")
        url[-1] = urllib.parse.quote(url[-1])
        url = "://".join(url)
        request = Request(url)
        request.get_method = lambda : 'HEAD'
        try:
            _ = urlopen(request)
            return url
        except HTTPError:
            return None

    def get_pyvers_name(self, url, cuda_version):
        """Checks if a provided url is available for a given cuda version

            It checks what package is available and is compatible with the available platforms
            returned by the pip

            Parameters
            ----------
            `url`: str
                Package url to be tested. `{cuda_v}` is replaced by cuda_version and  `{platform}`
                by the platform tag
            `cuda_version`: str
                Cuda version used for this query
        """
        if isinstance(p.get_supported()[0], tuple):
            # old PIP returns tuple
            for py_ver in [(x, y, z) for (x, y, z) in p.get_supported() if y != 'none' and 'any' not in y]:
                py_ver = "-".join(py_ver)
                ret = self.test_request(url.format(platform=py_ver, cuda_v=cuda_version))
                if ret:
                    return ret
        else:
            # new PIP returns object
            for py_ver in [tag for tag in p.get_supported() if tag.abi != 'none' and tag.platform != 'any']:
                py_ver = str(py_ver)
                ret = self.test_request(url.format(platform=py_ver, cuda_v=cuda_version))
                if ret:
                    return ret
        return ""

all_packages = [PlainPackage("opencv-python", ["4.2.0.32"]),
                CudaPackage("cupy",
                        { "90"  : ["7.3.0"],
                          "100" : ["7.3.0"] },
                        "cupy-cuda{cuda_v}"),
                CudaPackage("mxnet",
                        { "90"  : ["1.6.0"],
                          "100" : ["1.5.1"] },
                        "mxnet-cu{cuda_v}"),
                CudaPackage("tensorflow-gpu",
                        { "90"  : [PckgVer("1.12.0", python_max_ver="3.7")],
                          "100" : [PckgVer("1.15.2",  python_max_ver="3.7"), PckgVer("2.1.0",  python_max_ver="3.7"), \
                                   "2.2.0"] }),
                CudaHttpPackage("torch",
                        { "90"  : ["http://download.pytorch.org/whl/cu{cuda_v}/torch-1.1.0-{platform}.whl"],
                          "100" : ["http://download.pytorch.org/whl/cu{cuda_v}/torch-1.4.0+cu{cuda_v}-{platform}.whl"] }),
                CudaHttpPackage("torchvision",
                        { "90"  : ["https://download.pytorch.org/whl/cu{cuda_v}/torchvision-0.3.0-{platform}.whl"],
                          "100" : ["https://download.pytorch.org/whl/cu{cuda_v}/torchvision-0.5.0+cu{cuda_v}-{platform}.whl"] }),
                CudaHttpPackage("paddle",
                        { "90"  : ["https://paddle-wheel.bj.bcebos.com/gcc54/latest-gpu-cuda9-cudnn7-openblas/paddlepaddle_gpu-latest-{platform}.whl"],
                          "100" : ["https://paddle-wheel.bj.bcebos.com/gcc54/latest-gpu-cuda10-cudnn7-openblas/paddlepaddle_gpu-latest-{platform}.whl"] })
               ]

all_packages_keys = [pckg.key for pckg in all_packages]

parser = argparse.ArgumentParser(description='Env setup helper')
parser.add_argument('--list', '-l', help='list configs', action='store_true', default=False)
parser.add_argument('--num', '-n', help='return number of all configurations possible', action='store_true', default=False)
parser.add_argument('--install', '-i', dest='install', type=int, help="get Nth configuration", default=-1)
parser.add_argument('--all', '-a', dest='getall', action='store_true', help='return packages in all versions')
parser.add_argument('--remove', '-r', dest='remove', help="list packages to remove", action='store_true', default=False)
parser.add_argument('--cuda', dest='cuda', default="90", help="CUDA version to use")
parser.add_argument('--use', '-u', dest='use', default=[], help="provide only packages from this list", nargs='*')
args = parser.parse_args()

def print_configs(cuda_version):
    """Prints all available configurations"""
    for pckg in all_packages:
        print("{}:".format(pckg.get_name(cuda_version)))
        for v in pckg.get_all_versions(cuda_version):
            print("\t{}".format(v))

def cal_num_of_configs(packages, cuda_version):
    """Calculates how many different version configurations are available for given
       packages and cuda version"""
    ret = 1
    for pckg in all_packages:
        if pckg.key in packages:
            ret *= pckg.get_num_of_version(cuda_version)
    return ret

def for_all_pckg(packages, fun):
    """Iterates over all packages, executes a fun returns all fun results as a list"""
    ret = []
    for pckg in all_packages:
        if pckg.key in packages:
            ret.append(fun(pckg))
    # add all remaining used packages with default versions
    additional = [v for v in packages if v not in all_packages_keys]
    return ret + additional

def get_remove_string(packages, cuda_version):
    """Creates pip remove string for given cuda version and package list"""
    # Remove only these which version we want to change
    ret = for_all_pckg(packages, lambda pckg: pckg.get_name(cuda_version))
    return " ".join(ret)

def get_all_strings(packages, cuda_version):
    """Prints all available configurations for given package list and cuda version"""
    ret = for_all_pckg(packages, lambda pckg: pckg.get_all_install_strings(cuda_version))
    return " ".join(ret)

def get_install_string(idx, packages, cuda_version):
    """Creates pip install string for given cuda version, variant number and package list"""
    ret = for_all_pckg(packages, lambda pckg: pckg.get_install_string(idx, cuda_version))
    # add all remaining used packages with default versions
    return " ".join(ret)

def main():
    global args
    if args.list:
        print_configs(args.cuda)
    elif args.num:
        print (cal_num_of_configs(args.use, args.cuda) - 1)
    elif args.remove:
        print (get_remove_string(args.use, args.cuda))
    elif args.getall:
        print(get_all_strings(args.use, args.cuda))
    elif args.install >= 0:
        print (get_install_string(args.install, args.use, args.cuda))

if __name__ == "__main__":
    main()

import requests
import json


class TBClient(object):

    def __init__(self, hostname="localhost", port=8889):
        self.hostname = hostname
        self.port = port
        self.url = self.hostname + ":" + str(self.port)
        # TODO use urlparse
        if not (self.url.startswith("http://") or
                self.url.startswith("https://")):
            self.url = "http://" + self.url

        # check server is working (not only up).
        try:
            assert(requests.get(self.url).ok)
        except requests.ConnectionError:
            raise ValueError("The server at {}:{}".format(self.hostname,
                                                          self.port) +
                             " does not appear to be up!")
        except AssertionError:
            raise RuntimeError("Something went wrong!" +
                               " Tensorboard may be the problem.")

    def get_experiments(self, xp=None):
        query = "/data"
        r = requests.get(self.url + query)
        if not r.ok:
            experiments = []
        else:
            experiments = json.loads(r.text)
        return experiments

    def add_scalar(self, xp, name, data):
        assert(len(data) == 3)
        query = "/data/scalars?xp={}&name={}".format(xp, name)
        r = requests.post(self.url + query, json=data)
        if not r.ok:
            raise ValueError("Something went wrong.")

    def get_scalars(self, xp, name):
        query = "/data/scalars?xp={}&name={}".format(xp, name)
        r = requests.get(self.url + query)
        if not r.ok:
            raise ValueError("Something went wrong.")
        return json.loads(r.text)

    def add_histogram(self, xp, name, data, tobuild=False):
        assert(len(data) == 3)
        if not self.check_histogram_data(data[2], tobuild):
            raise ValueError("Data was not provided in a valid format!")
        query = "/data/histograms?xp={}&name={}&tobuild={}".format(
            xp, name, str(tobuild).lower())
        r = requests.post(self.url + query, json=data)
        if not r.ok:
            raise ValueError("Something went wrong.")

    def get_histograms(self, xp, name):
        query = "/data/histograms?xp={}&name={}".format(xp, name)
        r = requests.get(self.url + query)
        if not r.ok:
            raise ValueError("Something went wrong.")
        return json.loads(r.text)

    def set_data(self, xp, force, data):
        query = "/data/backup?xp={}&force={}".format(
            xp, force)
        r = requests.post(self.url + query, json=data)
        if not r.ok:
            raise ValueError("Something went wrong.")

    def get_data(self, xp):
        query = "/data/backup?xp={}".format(xp)
        r = requests.get(self.url + query)
        if not r.ok:
            raise ValueError("Something went wrong.")
        return r.text

    def check_histogram_data(self, data, tobuild):
        if tobuild:
            return len(data) == 7
        # TODO should use a schema here
        # Note: all of these are sorted already
        expected = ["bucket", "bucket_limit", "max", "min", "num"]
        expected2 = ["bucket", "bucket_limit", "max", "min", "num",
                     "sum"]
        expected3 = ["bucket", "bucket_limit", "max", "min", "num",
                     "sum", "sum_squares"]
        expected4 = ["bucket", "bucket_limit", "max", "min", "num",
                     "sum_squares"]
        ks = tuple(data.keys())
        ks = sorted(ks)
        return (ks == expected or ks == expected2
                or ks == expected3 or ks == expected4)

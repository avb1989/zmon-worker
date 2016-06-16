#!/usr/bin/env python
# -*- coding: utf-8 -*-

# wrapper for kairosdb to access history data about checks

import logging
import requests

import tokens

from zmon_worker_monitor.builtins.plugins.distance_to_history import DistanceWrapper

from zmon_worker_monitor.adapters.ifunctionfactory_plugin import IFunctionFactoryPlugin, propartial

logger = logging.getLogger(__name__)


# will use OAUTH2_ACCESS_TOKEN_URL environment variable by default
# will try to read application credentials from CREDENTIALS_DIR
tokens.configure()
tokens.manage('uid', ['uid'])
tokens.start()

ONE_WEEK = 7 * 24 * 60 * 60
ONE_WEEK_AND_5MIN = ONE_WEEK + 5 * 60


class HistoryFactory(IFunctionFactoryPlugin):
    def __init__(self):
        super(HistoryFactory, self).__init__()
        # fields from configuration
        self.kairosdb_history_enabled = None

    def configure(self, conf):
        """
        Called after plugin is loaded to pass the [configuration] section in their plugin info file
        :param conf: configuration dictionary
        """
        self.url = conf.get('url')
        self.kairosdb_history_enabled = True if conf.get('kairosdb_history_enabled') in ('true', 'True', '1') else False

    def create(self, factory_ctx):
        """
        Automatically called to create the check function's object
        :param factory_ctx: (dict) names available for Function instantiation
        :return: an object that implements a check function
        """
        return propartial(HistoryWrapper,
                          url=self.url,
                          history_enabled=self.kairosdb_history_enabled,
                          check_id=factory_ctx['check_id'],
                          entities=factory_ctx['entity_id_for_kairos'])


def get_request(check_id, entities, time_from, time_to, aggregator='avg', sampling_size_in_seconds=300):
    r = {
        'metrics': [
            {
                'tags': {
                    'entity': entities
                },
                'name': 'zmon.check.{}'.format(check_id),
                'group_by': [
                    {
                        'name': 'tag',
                        'tags': [
                            'key'
                        ]
                    }
                ],
                'aggregators': [
                    {
                        'name': aggregator,
                        'align_sampling': True,
                        'sampling': {
                            'value': sampling_size_in_seconds,
                            'unit': 'seconds'
                        }
                    }
                ]
            }
        ],
        'cache_time': 0,
        'start_relative': {
            'value': time_from,
            'unit': 'seconds'
        },
        'end_relative': {
            'value': time_to,
            'unit': 'seconds'
        }
    }

    return r


class HistoryWrapper(object):
    def __init__(self, url=None, history_enabled=False, check_id='', entities=None, oauth2=False):
        if not url:
            raise RuntimeError('History wrapper improperly configure. URL is required.')

        self.url = url
        self.check_id = check_id

        if not entities:
            self.entities = []
        elif type(entities) == list:
            self.entities = entities
        else:
            self.entities = [entities]

        self.__enabled = bool(history_enabled)

        self.__session = requests.Session()
        if oauth2:
            self.__session.headers.update({'Authorization': 'Bearer {}'.format(tokens.get('uid'))})

    def result(self, time_from=ONE_WEEK_AND_5MIN, time_to=ONE_WEEK):
        if not self.__enabled:
            raise Exception('History() function disabled for now')

        # self.logger.info("history query %s %s %s", self.check_id, time_from, time_to)
        return self.__session.post(self.url,
                                   json=get_request(self.check_id, self.entities, int(time_from), int(time_to))).json()

    def get_one(self, time_from=ONE_WEEK_AND_5MIN, time_to=ONE_WEEK):
        if not self.__enabled:
            raise Exception('History() function disabled for now')

        # self.logger.info("history get one %s %s %s", self.check_id, time_from, time_to)
        return (self.__session
                .post(self.url, json=get_request(self.check_id, self.entities, int(time_from), int(time_to)))
                .json()['queries'][0]['results'][0]['values'])

    def get_aggregated(self, key, aggregator, time_from=ONE_WEEK_AND_5MIN, time_to=ONE_WEEK):
        if not self.__enabled:
            raise Exception('History() function disabled for now')

        # read the list of results
        query_result = (self.__session
                        .post(self.url, json=get_request(self.check_id, self.entities, int(time_from),
                                                         int(time_to), aggregator, int(time_from - time_to)))
                        .json()['queries'][0]['results'])

        # filter for the key we are interested in
        filtered_for_key = [x for x in query_result if x['tags'].get('key', [''])[0] == key]

        if not filtered_for_key:
            return_value = []
        else:
            return_value = [filtered_for_key[0]['values'][0][1]]

        # since we have a sample size of 'all in the time range', return only the value, not the timestamp.
        return return_value

    def get_avg(self, key, time_from=ONE_WEEK_AND_5MIN, time_to=ONE_WEEK):
        if not self.__enabled:
            raise Exception('History() function disabled for now')

        # self.logger.info("history get avg %s %s %s", self.check_id, time_from, time_to)
        return self.get_aggregated(key, 'avg', time_from, time_to)

    def get_std_dev(self, key, time_from=ONE_WEEK_AND_5MIN, time_to=ONE_WEEK):
        if not self.__enabled:
            raise Exception('History() function disabled for now')

        # self.logger.info("history get std %s %s %s", self.check_id, time_from, time_to)
        return self.get_aggregated(key, 'dev', time_from, time_to)

    def distance(self, weeks=4, snap_to_bin=True, bin_size='1h', dict_extractor_path=''):
        if not self.__enabled:
            raise Exception('History() function disabled for now')

        # self.logger.info("history distance %s %s ", self.check_id, weeks, bin_size)
        return DistanceWrapper(history_wrapper=self, weeks=weeks, bin_size=bin_size, snap_to_bin=snap_to_bin,
                               dict_extractor_path=dict_extractor_path)


if __name__ == '__main__':
    import logging

    logging.basicConfig(level=logging.DEBUG)
    zhistory = HistoryWrapper(None, None, None, 17, ['GLOBAL'])
    r = zhistory.result()
    logging.info(r)
    r = zhistory.get_one()
    logging.info(r)
    r = zhistory.get_aggregated('', 'avg')
    logging.info(r)

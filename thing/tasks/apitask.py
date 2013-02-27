"""
Defines an abstract APITask class with various helpful features like error handling
and explosions.
"""

import datetime
import hashlib
import os
import requests
import sys
import time

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from celery import Task
from celery.task.control import broadcast
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.cache import cache
from django.db import connections
from django.db.models import Max
from urlparse import urljoin

from thing.models import APIKey, APIKeyFailure, Event, TaskState
from thing.stuff import total_seconds

# ---------------------------------------------------------------------------

PENALTY_TIME = 12 * 60 * 60
PENALTY_MULT = 0.2

# ---------------------------------------------------------------------------

class APITask(Task):
    abstract = True

    # Logger instance
    _logger = get_task_logger(__name__)

    # Requests session so we get HTTP Keep-Alive
    _session = requests.Session()
    _session.headers.update({
        'User-Agent': 'EVEthing-tasks (keep-alive)',
    })
    # Limit each session to a single connection
    _session.mount('http://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))
    _session.mount('https://', requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1))

    # -----------------------------------------------------------------------

    def init(self, taskstate_id=None, apikey_id=None):
        """
        Tasks should call this in their run() method to initialise stuff.
        Returns False if anything bad happens.
        """

        # Clear the current query information so we don't bloat
        if settings.DEBUG:
            for db in settings.DATABASES.keys():
                connections[db].queries = []

        self._started = time.time()
        self._api_log = []
        self._cache_delta = None

        self._taskstate = None
        self.apikey = None
        self.root = None

        # Fetch TaskState
        if taskstate_id is not None:
            try:
                self._taskstate = TaskState.objects.get(pk=taskstate_id)
            except TaskState.DoesNotExist:
                self.log_error('Task not starting: TaskState %d has gone missing', taskstate_id)
                return False

        # Fetch APIKey
        if apikey_id is not None:
            try:
                self.apikey = APIKey.objects.select_related('corp_character__corporation').get(pk=apikey_id)
            except APIKey.DoesNotExist:
                return False
            else:
                # Still valid?
                if not self.apikey.valid:
                    return False

    # -----------------------------------------------------------------------

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Task exploded.
        """
        if self._taskstate is not None:
            self._taskstate_ready()

    # -----------------------------------------------------------------------

    def on_success(self, retval, task_id, args, kwargs):
        """
        Task finished without crashing.
        """
        if self._taskstate is not None:
            self._taskstate_ready()

        # Actually successful
        if retval is True:
            # If DEBUG is enabled, log a bunch of stuff
            if settings.DEBUG:
                total_api = sum(a[1] for a in self._api_log)
                self.log_warn('[API] %.3fs  %d requests', total_api, len(self._api_log))
                for url, runtime in self._api_log:
                    self.log_warn('%.3fs  %s', runtime, url)

                for db in sorted(settings.DATABASES.keys()):
                    self.log_warn('[%s] %.3fs  %d queries',
                        db,
                        sum(float(q['time']) for q in connections[db].queries),
                        len(connections[db].queries),
                    )
                    for query in connections[db].queries:
                        if len(query['sql']) > 500:
                            self.log_warn('%02.3fs  %s...', float(query['time']), query['sql'][:500])
                        else:
                            self.log_warn('%02.3fs  %s', float(query['time']), query['sql'])

    # -----------------------------------------------------------------------

    def _taskstate_ready(self):
        """
        Update the TaskState to the 'ready' state and set next_time to a suitable
        value.
        """
        utcnow = datetime.datetime.utcnow()
        self._taskstate.state = TaskState.READY_STATE
        self._taskstate.mod_time = utcnow

        # If we received valid data, _cache_delta - use that to calculate next_time
        if self._cache_delta is not None:
            self._taskstate.next_time = utcnow + self._cache_delta + datetime.timedelta(seconds=20)
        # No valid data? Try delaying for 30 minutes.
        else:
            self._taskstate.next_time = utcnow + datetime.timedelta(minutes=30)

        self._taskstate.save()

    # ---------------------------------------------------------------------------
    
    def fetch_api(self, url, params, use_auth=True, log_error=True):
        """
        Fetch API data either from the API cache (if cached) or from the actual
        API server, then parse the returned XML. Sort of handles errors.
        """
        utcnow = datetime.datetime.utcnow()

        # Add the API key information
        if use_auth:
            params['keyID'] = self.apikey.keyid

        # Check the API cache for this URL/params combo

        cache_key = self._get_cache_key(url, params)
        cached_data = cache.get(cache_key)
        
        # Data is not cached, fetch new data
        if cached_data is None:
            # Sleep now if we have to
            sleep_for = self._get_backoff()
            if sleep_for > 0:
                self.log_warn('Sleeping for %d seconds', sleep_for)
                time.sleep(sleep_for)
            
            # Add the vCode to params now
            if use_auth:
                params['vCode'] = self.apikey.vcode

            # Fetch the URL
            full_url = urljoin(settings.API_HOST, url)
            start = time.time()
            try:
                if params:
                    r = self._session.post(full_url, params)
                else:
                    r = self._session.get(full_url)
                data = r.text
            except Exception, e:
                self._increment_backoff(e)
                return False

            self._api_log.append((url, time.time() - start))

            # If the status code is bad return False
            if not r.status_code == requests.codes.ok:
                self._increment_backoff('Bad status code: %s' % (r.status_code))
                return False

        # Data is cached, use that
        else:
            data = cached_data

        # Parse the data if there is any
        if data:
            try:
                self.root = self.parse_xml(data)
            except Exception:
                return False

            current = self.parse_api_date(self.root.find('currentTime').text)
            until = self.parse_api_date(self.root.find('cachedUntil').text)
            self._cache_delta = until - current

            # If the data wasn't cached, cache it now
            if cached_data is None:
                if self.apikey is None:
                    cache_expires = total_seconds(self._cache_delta) + 10
                else:
                    # Work out if we need a cache multiplier for this key
                    last_seen = APIKey.objects.filter(keyid=self.apikey.keyid, vcode=self.apikey.vcode).aggregate(m=Max('user__userprofile__last_seen'))['m']
                    secs = max(0, total_seconds(utcnow - last_seen))
                    mult = 1 + (min(20, max(0, secs / PENALTY_TIME)) * PENALTY_MULT)

                    # Generate a delta for cache penalty value
                    cache_expires = max(0, total_seconds(self._cache_delta) * mult) + 10
                    self._cache_delta = datetime.timedelta(seconds=cache_expires)

                if cache_expires >= 0:
                    cache.set(cache_key, data, cache_expires)

            # Check for an error node in the XML
            error = self.root.find('error')
            if error is not None:
                if log_error:
                    self.log_error('%s: %s | %s -> %s', error.attrib['code'], error.text, current, until)

                # Permanent key errors
                if error.attrib['code'] in ('202', '203', '204', '205', '210', '212', '207', '220', '222', '223'):
                    now = datetime.datetime.now()

                    # Mark the key as invalid
                    self.apikey.invalidate()

                    # Log an error
                    self.log_error('[fetch_api] API key with keyID %d marked invalid!', self.apikey.keyid)

                    # Log an error event for the user
                    text = "Your API key #%d was marked invalid: %s %s" % (
                        self.apikey.id,
                        error.attrib['code'],
                        error.text
                    )
                    Event.objects.create(
                        user_id=self.apikey.user.id,
                        issued=now,
                        text=text,
                    )

                    # Log a key failure
                    fail_reason = '%s: %s' % (error.attrib['code'], error.text)
                    APIKeyFailure.objects.create(
                        user_id=self.apikey.user.id,
                        keyid=self.apikey.keyid,
                        fail_time=now,
                        fail_reason=fail_reason,
                    )

                    # Check if we need to punish this user for their sins
                    one_week_ago = now - datetime.timedelta(7)
                    count = APIKeyFailure.objects.filter(user=self.apikey.user, fail_time__gt=one_week_ago).count()
                    limit = getattr(settings, 'API_FAILURE_LIMIT', 3)
                    if limit > 0 and count >= limit:
                        # Disable their ability to add keys
                        profile = self.apikey.user.get_profile()
                        profile.can_add_keys = False
                        profile.save()

                        # Log that we did so
                        text = "Limit of %d API key failures per 7 days exceeded, you may no longer add keys." % (limit)
                        Event.objects.create(
                            user_id=self.apikey.user.id,
                            issued=now,
                            text=text,
                        )

                # Website is broken errors, trigger sleep
                elif error.attrib['code'] in ('901', '902', '1001'):
                    self._increment_backoff('API server seems broken')

                # Something very bad has happened
                elif error.attrib['code'] == '904':
                    self.log_error('Received 904 error, killing workers!')
                    broadcast('shutdown')

                return False

        return True
    
    # -----------------------------------------------------------------------

    def fetch_url(self, url, params):
        """
        Fetch a URL directly without any API magic.
        """
        start = time.time()
        try:
            if params:
                r = self._session.post(url, params)
            else:
                r = self._session.get(url)
            data = r.text
        except Exception, e:
            #self._increment_backoff(e)
            return False

        self._api_log.append((url, time.time() - start))
        
        # If the status code is bad return False
        if not r.status_code == requests.codes.ok:
            #self._increment_backoff('Bad status code: %s' % (r.status_code))
            return False

        return data

    # -----------------------------------------------------------------------

    def parse_xml(self, data):
        """
        Parse XML and return an ElementTree.
        """
        return ET.fromstring(data.encode('utf-8'))

    # -----------------------------------------------------------------------

    def _get_cache_key(self, url, params):
        """
        Get an MD5 hash of data to use as a cache key.
        """
        key_data = '%s:%s' % (url, repr(sorted(params.items())))
        h = hashlib.new('md5')
        h.update(key_data)
        return h.hexdigest()

    # -----------------------------------------------------------------------

    def _get_backoff(self):
        """
        Get a time in seconds for the current backoff value. Initialises cache
        keys to 0 if they have mysteriously disappeared.
        """
        backoff_count = cache.get('backoff_count')
        # Initialise the cache value if it's missing
        if backoff_count is None:
            cache.set('backoff_count', 0)
            cache.set('backoff_last', 0)
            return 0

        if backoff_count == 0:
            return 0

        # Calculate the sleep value and return it
        sleep_for = 3
        for i in range(min(6, backoff_count)):
            sleep_for *= 2

        return sleep_for

    def _increment_backoff(self, e):
        """
        Helper function to increment the backoff counter
        """
        # Initialise the cache value if it's missing
        if cache.get('backoff_count') is None:
            cache.set('backoff_count', 0)
            cache.set('backoff_last', 0)

        now = time.time()
        # if it hasn't been 5 minutes, increment the wait value
        if (now - cache.get('backoff_last')) < 300:
            cache.incr('backoff_count')
        else:
            cache.set('backoff_count', 0)

        cache.set('backoff_last', now)

        self.log_warn('Backoff value increased: %s', e)

    # -----------------------------------------------------------------------

    def get_cursor(self, db='default'):
        """
        Get a database connection cursor for db.
        """
        return connections[db].cursor()

    # -----------------------------------------------------------------------

    def parse_api_date(self, apidate):
        """
        Parse a date from API XML into a datetime object.
        """
        return datetime.datetime.strptime(apidate, '%Y-%m-%d %H:%M:%S')

    # -----------------------------------------------------------------------
    # Logging shortcut functions :v
    def log_error(self, text, *args):
        text = '[%s] %s' % (self.__class__.__name__, text)
        self._logger.error(text, *args)
    
    def log_warn(self, text, *args):
        text = '[%s] %s' % (self.__class__.__name__, text)
        self._logger.warn(text, *args)
    
    def log_info(self, text, *args):
        text = '[%s] %s' % (self.__class__.__name__, text)
        self._logger.info(text, *args)
    
    def log_debug(self, text, *args):
        text = '[%s] %s' % (self.__class__.__name__, text)
        self._logger.debug(text, *args)

# ---------------------------------------------------------------------------
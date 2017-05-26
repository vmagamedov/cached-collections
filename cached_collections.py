import time
import logging
import cPickle as pickle
from threading import RLock
from collections import Mapping, Sequence

from redis.connection import ConnectionError as RedisUnavailable


log = logging.getLogger(__name__)


class Cached(object):

    def __init__(self, redis_client, name, version, check_interval=10):
        self._redis_client = redis_client

        self.name = name
        self.version = version
        self.revision = None

        self._rlock = RLock()

        self._data_key = 'cached.%s.%s.data' % (name, version)
        self._revision_key = 'cached.%s.%s.revision' % (name, version)
        self._check_interval = check_interval
        self._cache = None
        self._last_checked = None

    def load(self):
        raise NotImplementedError

    def push(self):
        with self._rlock:
            data = self.load()
            raw_data = pickle.dumps(data, pickle.HIGHEST_PROTOCOL)
            pipe = self._redis_client.pipeline()
            pipe.set(self._data_key, raw_data)
            pipe.incr(self._revision_key)
            _, self.revision = pipe.execute()
            self._cache = data
            log.debug('Pushed new revision of "%s", version "%s"'
                      % (self.name, self.version))

    def pull(self):
        with self._rlock:
            revision = self._redis_client.get(self._revision_key)
            if revision is None:
                # nothing to pull, pushing initial revision
                self.push()
                return

            raw_data = self._redis_client.get(self._data_key)
            self._cache = pickle.loads(raw_data)
            self.revision = int(revision)
            log.debug('Pulled latest revision of "%s", version "%s"'
                      % (self.name, self.version))

    def purge(self):
        with self._rlock:
            pipe = self._redis_client.pipeline()
            pipe.delete(self._data_key)
            pipe.delete(self._revision_key)
            pipe.execute()
            self.revision = None
            self._cache = None
            self._last_checked = None
            log.debug('Purged "%s", version "%s"' % (self.name, self.version))

    def _maybe_pull(self):
        if self._last_checked is not None:
            if time.time() - self._last_checked < self._check_interval:
                return

        with self._rlock:
            if self.revision is not None:
                log.debug('Checking new revision of "%s"' % self.name)
                try:
                    current_revision = self._redis_client.get(self._revision_key)
                except RedisUnavailable:
                    return
                if current_revision and int(current_revision) <= self.revision:
                    self._last_checked = time.time()
                    return

            self.pull()
            self._last_checked = time.time()


class CachedMappingMixin(Mapping):

    def __getitem__(self, key):
        self._maybe_pull()
        return self._cache[key]

    def __len__(self):
        self._maybe_pull()
        return len(self._cache)

    def __iter__(self):
        self._maybe_pull()
        return iter(self._cache)

    # optional speedup
    def values(self):
        self._maybe_pull()
        return self._cache.values()

    # optional speedup
    def itervalues(self):
        self._maybe_pull()
        return self._cache.itervalues()

    # optional speedup
    def items(self):
        self._maybe_pull()
        return self._cache.items()

    # optional speedup
    def iteritems(self):
        self._maybe_pull()
        return self._cache.iteritems()


class CachedSequenceMixin(Sequence):

    def __getitem__(self, index):
        self._maybe_pull()
        return self._cache[index]

    def __len__(self):
        self._maybe_pull()
        return len(self._cache)

    def __iter__(self):
        self._maybe_pull()
        return iter(self._cache)


class CachedMapping(Cached, CachedMappingMixin):
    pass


class CachedSequence(Cached, CachedSequenceMixin):
    pass


undefined = object()


class CacheView(object):

    def __init__(self, cached_collection):
        self._cached_collection = cached_collection
        self._revision = undefined
        self._cache = None

    def load(self, cached_collection):
        raise NotImplementedError

    def _maybe_pull(self):
        self._cached_collection._maybe_pull()
        if self._revision != self._cached_collection.revision:
            self._cache = self.load(self._cached_collection)
            self._revision = self._cached_collection.revision


class CachedMappingView(CacheView, CachedMappingMixin):
    pass


class CachedSequenceView(CacheView, CachedSequenceMixin):
    pass


class _view_descriptor(object):
    view_cls = None

    def __init__(self, func):
        self.__name__ = func.__name__
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            return self

        view = instance.__dict__.get(self.__name__, undefined)
        if view is undefined:
            view_cls = type(self.__name__, (self.view_cls,), {
                'load': lambda *a, **kw: self.func(instance),
            })
            view = view_cls(instance)
            instance.__dict__[self.__name__] = view
        return view


class mapping_view(_view_descriptor):
    view_cls = CachedMappingView


class sequence_view(_view_descriptor):
    view_cls = CachedSequenceView

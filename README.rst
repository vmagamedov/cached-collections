Synchronized between processes in-memory cache for storing frequently used data

Installation
~~~~~~~~~~~~

.. code-block:: shell

  $ pip install git+https://github.com/vmagamedov/cached-collections

Usage
~~~~~

.. code-block:: python

  from operator import attrgetter
  from itertools import groupby
  from collections import namedtuple

  from app import SOURCE_CODE_VERSION
  from app.db import db, redis
  from app.model import Entity

  from cached_collections import CachedMapping, mapping_view


  CachedEntity = namedtuple('CachedEntity', 'id, parent_id, name')


  class CachedEntityMapping(CachedMapping):

      def load(self):
          rows = (
              db.session.query(Entity.id, Entity.parent_id, Entity.name)
              .all()
          )
          return {row.id: CachedEntity(*row) for row in rows}

      # Views are used to avoid cached data duplication or unnecessary heavy
      # computations every time, when you need to lookup cached data in a
      # different way. Views will be automatically and lazily recalculated
      # every time cached data changes. So everything will be in sync and
      # computed only once.
      @mapping_view
      def by_parent_id(self):
          entities = sorted(self.values(), key=attrgetter('parent_id'))
          grouped = groupby(entities, attrgetter('parent_id'))
          return {key: tuple(grouper) for key, grouper in grouped}


  # SOURCE_CODE_VERSION or something similar is used to safely unpickle
  # cached in the Redis data
  cached_entity_mapping = CachedEntityMapping(redis, 'entity-name',
                                              SOURCE_CODE_VERSION)

  # Push will make cached data available to all application processes.
  # Every time you push cached collection:
  # - data will be loaded from the database;
  # - loaded data will be stored in the Redis;
  # - revision number of the cache will be incremented;
  # - other processes will detect revision number change and will load new
  #   data from the Redis.
  # It is recommended to push cached collections before deploying new
  # application version.
  cached_entity_mapping.push()


  def print_entity_and_its_children(entity_id):
      cached_entity = cached_entity_mapping[entity_id]
      print(cached_entity.name)
      for child in cached_entity_mapping.by_parent_id[entity_id]:
          print(child.name)

  # Purge will delete old version of the cached collections in the Redis. It is
  # recommended to leave two-three or more cache versions in the Redis in order
  # to safely make deployment rollbacks or deploy from multiple branches.
  CachedEntityMapping(redis, cached_entity_mapping.name, previous_version).purge()

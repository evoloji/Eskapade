# **********************************************************************************
# * Project: Eskapade - A python-based package for data analysis                   *
# * Class  : ValueCounter                                                          *
# * Created: 2017/03/02                                                            *
# * Description:                                                                   *
# *      Algorithm to do value_counts() on single columns of a pandas
# *      dataframe, or groupby().size() on multiple columns, both returned
# *      as dictionaries. It is possible to do cleaning of these dicts by
# *      rejecting certain keys or removing inconsistent data types.
# *      Numeric and timestamp columns are converted to bin indices before
# *      the binning is applied.
# *      Results are stored as 1D Histograms or as ValueCounts objects.
# *                                                                                *
# * Authors:                                                                       *
# *      KPMG Big Data team, Amstelveen, The Netherlands                           *
# *                                                                                *
# * Redistribution and use in source and binary forms, with or without             *
# * modification, are permitted according to the terms listed in the file          *
# * LICENSE.                                                                       *
# **********************************************************************************

from eskapade import ProcessManager, ConfigObject, Link, DataStore, StatusCode
from collections import Counter
import numpy as np
import pandas as pd
from eskapade.analysis.histogram import Histogram, ValueCounts

# numeric datatypes get converted to an index, which is then used for
# value counting
NUMERIC_SUBSTR = [
    np.dtype('int'),
    np.dtype('float'),
    np.dtype('double'),
    np.dtype('datetime64[ns]')]
# string datatype get treated as categories, and are not converted to an index
STRING_SUBSTR = [np.dtype('str'), np.dtype('object'), np.dtype('bool')]


NUM_NS_DAY = 24 * 3600 * int(1e9)


class ValueCounter(Link):
    """ ValueCounter does value_counts() on single or multiple columns of a pandas dataframe

    Algorithm to do value_counts() on single columns of a pandas
    dataframe, or groupby().size() on multiple columns, both returned
    as same-style dictionaries. Numeric and timestamp columns are converted
    to bin indices before the binning is applied. The binning can be provided as input.
    It is possible to do cleaning of these dicts by rejecting certain keys or removing
    inconsistent data types. Results are stored as 1D Histograms or as ValueCounts objects.

    Example is available in: tutorials/esk303_histogram_filling_plotting.py
    """

    def __init__(self, **kwargs):
        """Store and do basic check on the attributes of link ValueCounter

        :param str name: name of link
        :param str read_key: key of input data to read from data store
        :param str store_key_counts: key of output data to store ValueCounts objects in data store
        :param str store_key_hists: key of output data to store histograms in data store
        :param list columns: colums to pick up from input data
        :param dict bin_specs: dictionaries used for rebinning numeric or timestamp columns.

        Example bin_specs dictionary is:

        >>> bin_specs = { 'x': { 'bin_width': 1, 'bin_offset': 0 }, \
                          'y': { 'bin_edges': [0,2,3,4,5,7,8] }, \
                          'date': { 'bin_width': np.timedelta64(30,'D'), \
                                    'bin_offset': np.datetime64('2010-01-04') } }

        :param bool num_ts_to_bin_index: convert numeric and timestamp columns to and index (to group on). Default is True.
        :param bool num_ts_to_bin_center: convert numeric and timestamp columns to a center-of-bin value (to group on). Default is False. Inverse of num_ts_to_bin_index.
        :param dict datatype: dict of datatypes of the columns to study from dataframe. If not provided, try to determine datatypes directy from dataframe.
        :param bool store_at_finalize: Store histograms and/or ValueCount object in datastore at finalize(), not at execute(). Useful when looping over datasets. Default is False.
        :param bool drop_inconsistent_key_types: cleanup histograms and/or ValueCount objects by removing alls bins/keys with inconsistent datatypes.
        By default compare with data types in datatype dictionary.
        :param drop_keys dict: dictionary used for dropping specific keys from created value_counts dictionaries.

        Example drop_keys dictionary is:

        >>> drop_keys = { 'x': [1,4,8,19], \
                          'y': ['apple', 'pear', 'tomato'] \
                          'x:y': [(1,'apple'),(19,'tomato')] }
        """

        # initialize Link, pass name from kwargs
        Link.__init__(self, kwargs.pop('name', 'ValueCounter'))

        # process and register all relevant kwargs. kwargs are added as attributes of the link.
        # second arg is default value for an attribute. key is popped from
        # kwargs.
        self._process_kwargs(kwargs,
                             read_key=None,
                             store_key_counts=None,
                             store_key_hists=None,
                             columns=[],
                             bin_specs={},
                             num_ts_to_bin_index=True,
                             num_ts_to_bin_center=False,
                             datatype={},
                             store_at_finalize=False,
                             drop_inconsistent_key_types=True,
                             drop_keys={})

        # check residual kwargs. exit if any present.
        self.check_extra_kwargs(kwargs)

        self._unit_bin_specs = {'bin_width': 1, 'bin_offset': 0}
        self._unit_timestamp_specs = {'bin_width': np.timedelta64(30, 'D'),
                                      'bin_offset': np.datetime64('2010-01-04')}
        # these get filled during execution
        self._counts = {}
        self._valcnts = {}
        self._hists1d = {}

    def initialize(self):
        """Initialize and (further) check the assigned attributes of ValueCounter"""

        # check basic attribute settings
        assert isinstance(self.read_key, str) and len(self.read_key), \
            'read_key has not been set correctly.'
        if self.store_key_hists is not None:
            assert isinstance(self.store_key_hists, str) and len(self.store_key_hists), \
                'store_key_hists has not been set to string.'
        if self.store_key_counts is not None:
            assert isinstance(self.store_key_counts, str) and len(self.store_key_counts), \
                'store_key_counts has not been set to string.'
        assert self.store_key_hists is not None or self.store_key_counts is not None, \
            'ERROR. No store key has been set.'

        # numerical or timestamp variables get converted to either indices or
        # bin center values. value counts happens based on the converted vars.
        assert self.num_ts_to_bin_index is not self.num_ts_to_bin_center, \
            'num_ts_to_bin_index <%s> cannot equal num_ts_to_bin_center <%s>' % \
            (self.num_ts_to_bin_index, self.num_ts_to_bin_center)
        if self.num_ts_to_bin_index:
            self.log().info('Numeric and time stamp observables will be converted to integer indices.')
        elif self.num_ts_to_bin_center:
            self.log().info('Numeric and time stamp observables will be converted to bin centers.')

        # default histogram creation is at execute(). At finalize is useful for
        # looping over datasets.
        if self.store_at_finalize:
            self.log().debug('Creating histograms from 1d value counts at finalize, not execute.')

        # check that columns are set correctly.
        for i, c in enumerate(self.columns):
            if isinstance(c, str):
                self.columns[i] = [c]
            assert isinstance(self.columns[
                              i], list), 'columns <%s> needs to be a string or list of strings.' % self.columns[i]

        # construct the empty value count dicts.
        # updated in execute()
        for c in self.columns:
            name = ':'.join(c)
            self._counts[name] = Counter()

        # check for supported data types
        for k in self.datatype.keys():
            try:
                self.datatype[k] = np.dtype(self.datatype[k]).type
                if (self.datatype[k] is np.string_) or (
                        self.datatype[k] is np.object_):
                    self.datatype[k] = str
            except:
                raise Exception(
                    'ERROR. Unknown assigned datatype to variable <%s>.' %
                    k)

        return StatusCode.Success

    def execute(self):
        """Execute ValueCounter

        Does 4 things:

        * check presence and data type of requested columns
        * numerical and timestamp variables are converted to indices (for grouping by)
        * do the actual value counting based on categories and created indices
        * then convert to histograms and add to datastore
        """

        proc_mgr = ProcessManager()
        ds = proc_mgr.service(DataStore)

        # basic checks on contensts of the data frame
        assert self.read_key in list(
            ds.keys()), 'Key %s not in DataStore.' % self.read_key
        df = ds[self.read_key]
        if not isinstance(df, pd.DataFrame):
            raise Exception('Retrieved object not of type pandas DataFrame.')
        assert len(df.index) > 0, 'dataframe %s is empty.' % self.read_key

        # 1. check presence and data type of requested columns
        # sort columns into numerical and category based
        # numerical variables are converted to indices below
        strcols = []
        numcols = []
        for c in self.columns:
            for col in c:
                assert col in df.columns, 'column <%s> not in dataframe <%s>' % (
                    col, self.read_key)
                dt = df[col].dtype
                if not col in self.datatype:
                    self.datatype[col] = dt.type
                    if (self.datatype[col] is np.string_) or (
                            self.datatype[col] is np.object_):
                        self.datatype[col] = str
                assert dt in STRING_SUBSTR or dt in NUMERIC_SUBSTR, \
                    'ERROR. Cannot process column <%s> of data type <%s>.' % (
                        col, dt)
                is_number = isinstance(dt.type(), np.number)
                is_timestamp = isinstance(dt.type(), np.datetime64)
                colset = numcols if is_number or is_timestamp else strcols
                if col not in colset:
                    colset.append(col)
                self.log().debug(
                    'Datatype of column <%s> is <%s>.' %
                    (col, self.datatype[col]))

        # 2. numerical variables are converted to indices here
        # make temp df for value counting (used below)
        idf = df[strcols].copy(deep=False)
        for col in numcols:
            self.log().debug(
                'Converting column <%s> of type <%s> to index.' %
                (col, self.datatype[col]))
            # find column specific bin_specs. if not found, use dict of default
            # values.
            dt = df[col].dtype
            is_number = isinstance(dt.type(), np.number)
            is_timestamp = isinstance(dt.type(), np.datetime64)
            bin_specs = self.bin_specs.get(
                col, self._unit_bin_specs if is_number else self._unit_timestamp_specs)
            if self.num_ts_to_bin_index:
                idf[col] = df[col].apply(value_to_bin_index, **bin_specs)
            elif self.num_ts_to_bin_center:
                idf[col] = df[col].apply(value_to_bin_center, **bin_specs)

        # 3. do the actual value counting based on categories and created
        # indices
        for c in self.columns:
            name = ':'.join(c)
            self.log().debug('Value counting column(s) <%s>.' % (name))
            # value_counts() is faster than groupby().size(), but only works for series (1d).
            # else use groupby() for multi-dimensions
            g = idf.groupby(by=c).size() if len(
                c) > 1 else idf[c[0]].value_counts()
            counts = Counter(g.to_dict())
            # remove specific keys from dict, if so requested
            counts = self.drop_requested_keys(name, counts)
            self._counts[name].update(counts)
        # cleanup temp df
        del idf

        # 4. storage
        # then convert to histograms and add to datastore
        if self.store_key_hists is not None and not self.store_at_finalize:
            self.make_and_store_1dhistograms()
        # store the Counter objects as well?
        if self.store_key_counts is not None and not self.store_at_finalize:
            self.make_and_store_valuecounts()

        return StatusCode.Success

    def finalize(self):
        """Clearing up ValueCounter

        Store Histograms and/or created ValueCounts objects here, if requested so.
        """

        # convert to histograms and add to datastore
        if self.store_key_hists is not None and self.store_at_finalize:
            self.make_and_store_1dhistograms()
        # store the Counter objects as well?
        if self.store_key_counts is not None and self.store_at_finalize:
            self.make_and_store_valuecounts()

        # cleanup
        if self.store_key_counts is None:
            del self._valcnts
        if self.store_key_hists is None:
            del self._hists1d
        del self._counts

        return StatusCode.Success

    def make_and_store_valuecounts(self):
        """Make ValueCount objects, clean them up, and store them """

        # construct hist from value counts
        for c in self.columns:
            name = ':'.join(c)
            vc = ValueCounts(c, c, self._counts[name])
            # remove all items from Counters where the key is not of correct datatype.
            # e.g. in Counter dict of ints, remove any non-ints that may arise
            # from dq issues.
            if self.drop_inconsistent_key_types:
                vc = self.drop_inconsistent_keys(c, vc)
            self._valcnts[name] = vc

        proc_mgr = ProcessManager()
        ds = proc_mgr.service(DataStore)
        ds[self.store_key_counts] = self._valcnts
        return

    def make_and_store_1dhistograms(self):
        """Make histograms of all 1d value_counts, clean them up, and store them"""

        # construct hist from value counts
        for c in self.columns:
            if len(c) != 1:
                continue
            name = ':'.join(c)
            dt = np.dtype(self.datatype[name]).type()
            is_number = isinstance(dt, np.number)
            is_timestamp = isinstance(dt, np.datetime64)
            # bin_specs is used for converting index back to original var in
            # histogram class.
            bin_specs = {}
            if self.num_ts_to_bin_index:
                if is_number:
                    bin_specs = self.bin_specs.get(name, self._unit_bin_specs)
                elif is_timestamp:
                    bin_specs = self.bin_specs.get(
                        name, self._unit_timestamp_specs)
            h = Histogram(self._counts[name], variable=name, datatype=self.datatype[name],
                          bin_specs=bin_specs)

            # remove all items from Counters where the key is not of correct datatype.
            # e.g. in Counter dict of ints, remove any non-ints that may arise
            # from dq issues.
            if self.drop_inconsistent_key_types:
                h = self.drop_inconsistent_keys(c, h)
            self._hists1d[name] = h
        # storage
        proc_mgr = ProcessManager()
        ds = proc_mgr.service(DataStore)
        ds[self.store_key_hists] = self._hists1d

    def drop_requested_keys(self, name, counts):
        """ Drop requested keys from value_counts dictionary.

        :param string name: key of drop_keys dict to get array of keys to be dropped.
        :param dict counts: value_counts dictionary to drop specific keys from.
        """
        # drop requested keys
        if name in self.drop_keys:
            keys_to_drop = self.drop_keys[name]
            assert isinstance(
                keys_to_drop, list), 'drop_keys value needs to be a list of values.'
            for key in keys_to_drop:
                if key in counts:
                    self.log().debug(
                        'Removing key: %s with value: %s, as requested.' %
                        (key, counts[key]))
                    del counts[key]
        return counts

    def drop_inconsistent_keys(self, c, obj):
        """ Drop inconsistent keys from ValueCounts or Histogram object.

        :param list c: columns key to retrieve desired datatypes.
        :param object obj: ValueCounts or Histogram object to drop inconsistent keys from.
        """
        # has array been converted first? if so, set correct comparison
        # datatype
        comp_dtype = []
        for col in c:
            dt = np.dtype(self.datatype[col]).type()
            is_converted = isinstance(
                dt, np.number) or isinstance(
                dt, np.datetime64)
            if is_converted and self.num_ts_to_bin_index:
                comp_dtype.append(np.int64)
            else:
                comp_dtype.append(self.datatype[col])
        # keep only keys of types in comp_dtype
        obj.remove_keys_of_inconsistent_type(prefered_key_type=comp_dtype)
        return obj


def value_to_bin_index(val, **kwargs):
    """ function to convert a numeric or timestamp column to an integer bin index.

    :param bin_width: bin_width value needed to convert column to an integer bin index.
    :param bin_offset: bin_offset value needed to convert column to an integer bin index.
    """
    try:
        # NOTE this notation also works for timestamps
        bin_width = kwargs.get('bin_width', 1)
        bin_offset = kwargs.get('bin_offset', 0)
        bin_index = int(np.floor((val - bin_offset) / bin_width))
        return bin_index
    except:
        pass
    return val


def value_to_bin_center(val, **kwargs):
    """ function to convert a numeric or timestamp column to a common bin center value.

    :param bin_width: bin_width value needed to convert column to a common bin center value.
    :param bin_offset: bin_offset value needed to convert column to a common bin center value.
    """
    try:
        # NOTE this notation also works for timestamps, and does not change the
        # unit
        bin_width = kwargs.get('bin_width', 1)
        bin_offset = kwargs.get('bin_offset', 0)
        bin_index = int(np.floor((val - bin_offset) / bin_width))
        obj_type = type(bin_width)
        return bin_offset + obj_type((bin_index + 0.5) * bin_width)
    except:
        pass
    return val
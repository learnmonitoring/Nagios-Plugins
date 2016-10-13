#!/usr/bin/env python
#  vim:ts=4:sts=4:sw=4:et
#
#  Author: Hari Sekhon
#  Date: 2016-10-12 22:42:37 +0100 (Wed, 12 Oct 2016)
#
#  https://github.com/harisekhon/nagios-plugins
#
#  License: see accompanying Hari Sekhon LICENSE file
#
#  If you're using my code you're welcome to connect with me on LinkedIn
#  and optionally send me feedback to help steer this or other code I publish
#
#  https://www.linkedin.com/in/harisekhon
#

"""

Nagios Plugin to check a specific HBase table's cell value via the Thrift API

Checks:

1. checks HBase table is enabled
2. reads latest HBase cell value for the given table, row key and column family:qualifier
3. checks cell's returned value against expected regex (optional)
4. checks cell's returned value against warning/critical range thresholds (optional)
   raises warning/critical if the value is outside thresholds or not a floating point number
5. outputs the query time to a given precision for reporting and graphing
6. optionally outputs the cell's value for graphing purposes

Tested on Apache HBase 1.0.3, 1.1.6, 1.2.2

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
#from __future__ import unicode_literals

import os
import re
import sys
import socket
import time
import traceback
try:
    # pylint: disable=wrong-import-position
    import happybase
    # weird this is only importable after happybase, must global implicit import
    from Hbase_thrift import IOError as HBaseIOError # pylint: disable=import-error
    from thriftpy.thrift import TException as ThriftException
except ImportError as _:
    print('Happybase / thrift module import error - did you forget to build this project?\n\n'
          + traceback.format_exc(), end='')
    sys.exit(4)
srcdir = os.path.abspath(os.path.dirname(__file__))
libdir = os.path.join(srcdir, 'pylib')
sys.path.append(libdir)
try:
    # pylint: disable=wrong-import-position
    from harisekhon.utils import log, qquit, ERRORS, isFloat, isList, support_msg_api
    from harisekhon.utils import validate_host, validate_port, validate_regex, validate_units
    from harisekhon.hbase.utils import validate_hbase_table, validate_hbase_rowkey, validate_hbase_column_qualifier
    from harisekhon import NagiosPlugin
except ImportError as _:
    print('harisekhon module import error - did you try copying this program out without the adjacent pylib?\n\n'
          + traceback.format_exc(), end='')
    sys.exit(4)

__author__ = 'Hari Sekhon'
__version__ = '0.3'


class CheckHBaseCell(NagiosPlugin):

    def __init__(self):
        # Python 2.x
        super(CheckHBaseCell, self).__init__()
        # Python 3.x
        # super().__init__()
        self.conn = None
        self.host = None
        self.port = None
        self.table = None
        self.row = None
        self.column = None
        self.expected = None
        self.precision = 4
        self.graph = False
        self.units = None
        self.list_tables = False
        self.msg = 'msg not defined'
        self.ok()

    def add_options(self):
        self.add_hostoption(name='HBase Thrift Server', default_host='localhost', default_port=9090)
        self.add_opt('-T', '--table', help='Table to query')
        self.add_opt('-R', '--row', help='Row to query')
        self.add_opt('-C', '--column', help='Column family:qualifier to query')
        self.add_opt('-e', '--expected', help='Expected regex for the cell\'s value. Optional')
        self.add_thresholds()
        self.add_opt('-p', '--precision', default=4, metavar='int',
                     help='Precision for query timing in decimal places (default: 4)')
        self.add_opt('-g', '--graph', action='store_true', help="Graph the cell's value. Optional, use only if a " +
                     "floating point number is normally returned for it's values, otherwise will print NaN " +
                     "(Not a Number). The reason this is not determined automatically is because keys that change " +
                     "between floats and non-floats will result in variable numbers of perfdata tokens which will " +
                     "break PNP4Nagios")
        self.add_opt('-u', '--units', help="Units to use if graphing cell's value. Optional")
        self.add_opt('-l', '--list', action='store_true', help='List tables and exit')

    def process_options(self):
        self.no_args()
        self.host = self.get_opt('host')
        self.port = self.get_opt('port')
        self.row = self.get_opt('row')
        self.column = self.get_opt('column')
        self.expected = self.get_opt('expected')
        self.precision = self.get_opt('precision')
        self.graph = self.get_opt('graph')
        self.units = self.get_opt('units')
        validate_host(self.host)
        validate_port(self.port)
        self.list_tables = self.get_opt('list')
        if not self.list_tables:
            self.table = self.get_opt('table')
            validate_hbase_table(self.table, 'hbase')
            validate_hbase_rowkey(self.row)
            validate_hbase_column_qualifier(self.column)
        if self.expected is not None:
            validate_regex('expected value', self.expected)
        if self.units is not None:
            validate_units(self.units)
        self.validate_thresholds(optional=True, positive=False)

    def run(self):
        connect_time = self.connect()
        if self.list_tables:
            tables = self.get_tables()
            print('HBase Tables:\n\n' + '\n'.join(tables))
            sys.exit(ERRORS['UNKNOWN'])
        (value, query_time) = self.check_cell()
        self.output_perfdata(value, connect_time, query_time)

    def connect(self):
        log.info('connecting to HBase Thrift Server at %s:%s', self.host, self.port)
        try:
            start = time.time()
            self.conn = happybase.Connection(host=self.host, port=self.port, timeout=10 * 1000)  # ms
            connect_time = time.time() - start
            log.info('connected in %s secs', connect_time)
        except (socket.timeout, ThriftException) as _:
            qquit('CRITICAL', _)
        return connect_time

    def get_tables(self):
        try:
            tables = self.conn.tables()
            if not isList(tables):
                qquit('UNKNOWN', 'table list returned is not a list! ' + support_msg_api())
            return tables
        except (socket.timeout, ThriftException) as _:
            qquit('CRITICAL', 'error while trying to get table list: {0}'.format(_))

    def check_cell(self):
        log.info('checking table \'%s\'', self.table)
        cells = []
        query_time = None
        try:
            if not self.conn.is_table_enabled(self.table):
                qquit('CRITICAL', "table '{0}' is not enabled!".format(self.table))
            table = self.conn.table(self.table)
            log.info('getting cells')
            start = time.time()
            cells = table.cells(self.row, self.column, versions=1)
            query_time = time.time() - start
            log.info('queried in %s secs', query_time)
            log.info('finished, closing connection')
            self.conn.close()
        except HBaseIOError as _:
            #if 'org.apache.hadoop.hbase.TableNotFoundException' in _.message:
            if 'TableNotFoundException' in _.message:
                qquit('CRITICAL', 'table \'{0}\' does not exist'.format(self.table))
            elif 'NoSuchColumnFamilyException' in _.message:
                qquit('CRITICAL', 'column family \'{0}\' does not exist'.format(self.column))
            else:
                qquit('CRITICAL', _)
        except (socket.timeout, ThriftException) as _:
            qquit('CRITICAL', _)

        cell_info = "HBase table '{0}' row '{1}' column '{2}'".format(self.table, self.row, self.column)

        log.debug('cells returned: %s', cells)
        if not isList(cells):
            qquit('UNKNOWN', 'non-list returned for cells. ' + support_msg_api())

        if len(cells) < 1:
            qquit('CRITICAL', "no cell value found in {0}, does row / column family combination exist?".
                  format(cell_info))
        elif len(cells) > 1:
            qquit('UNKNOWN', "more than one cell returned! " + support_msg_api())

        value = cells[0]
        log.info('value = %s', value)

        self.msg = "cell value = '{0}' for {1}".format(value, cell_info)

        if self.expected:
            log.info("checking cell's value '{0}' against expected regex '{1}'".format(value, self.expected))
            if not re.search(self.expected, value):
                qquit('CRITICAL', "cell value '{0}' (expected regex '{1}') for {2}".format(value, self.expected,
                                                                                           cell_info))
        return (value, query_time)

    def output_perfdata(self, value, connect_time, query_time):
        if isFloat(value):
            log.info('value is float, checking thresholds')
            self.check_thresholds(value)
        self.msg += ' | '
        if self.graph:
            if isFloat(value):
                self.msg += 'value={0}'.format(value)
                if self.units:
                    self.msg += str(self.units)
                self.msg += self.get_perf_thresholds()
            else:
                self.msg += 'value=NaN'
        self.msg += ' connect_time={0:0.{2}f}s query_time={1:0.{2}f}s'.format(connect_time,
                                                                              query_time, self.precision)


if __name__ == '__main__':
    CheckHBaseCell().main()

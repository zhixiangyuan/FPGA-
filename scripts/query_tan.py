"""Print the summary of an eLinx timing database (`.tan.pb`, SQLite format).

Usage: python scripts/query_tan.py <path-to-tan.pb>
"""
import sqlite3
import sys


def main():
    path = sys.argv[1]
    conn = sqlite3.connect('file:' + path + '?mode=ro', uri=True)
    row = next(conn.execute(
        'select setup_wns,setup_tns,setup_number_failing_endpoints,setup_number_endpoints,'
        'hold_wns,hold_tns,hold_number_failing_endpoints,hold_number_endpoints '
        'from elinx_timing_summary'))
    print('setup: wns=%s ps tns=%s ps failing=%s/%s' % (row[0], row[1], row[2], row[3]))
    print('hold : wns=%s ps tns=%s ps failing=%s/%s' % (row[4], row[5], row[6], row[7]))
    for name, period, fmax, setup, fail_ends, hold, hold_fail in conn.execute(
            'select name,period,fmax,setup_worst_slack,setup_fail_ends,'
            'hold_worst_slack,hold_fail_ends from elinx_intra_clock_summary'):
        print('clock: %s period=%s ps fmax=%.3f MHz setup=%s ps (failing %s) '
              'hold=%s ps (failing %s)' % (name, period, fmax, setup, fail_ends, hold, hold_fail))
    print('slowest setup path:')
    for slack, levels, src, dst in conn.execute(
            'select slack,levels,from_cell_name,to_cell_name '
            'from elinx_intra_clock_longest_sync_path_report order by slack limit 3'):
        print('  %s ps, %s levels: %s -> %s' % (slack, levels, src, dst))


if __name__ == '__main__':
    main()

#!/usr/bin/env python
#
# NAME
#   mkqif.py - convert downloaded finance CSV files to QIF files.
#
# SYNOPIS
#   python mkqif.py [-c cutoff_date] [--cutoff-delta n]
#                   [-d source_dir] [-e effective_date]
#                   [-f config_file] [-i fi_name[,...]] [-n] [--no-date-check]
#                   [-o output_dir] [-s] [-v] [-x] [fi_name,csv_file ...]
#
# See README.md for a full description.
#
# MODIFICATION HISTORY
# Mnemonic     Date     Rel   Who
# mkqif.py     20161030 1.0   mpw
#   Created.
# mkqif.py     20161101 2.0   mpw
#   Revamped to use objects, rather than dictionaries, to hold
#   financial institution specific information and processing.
# mkqif.py     20170204 2.1   mpw
#   JL changed format of downloaded CSV file.  It is now using the
#   ISO8859-1 (latin1) character set, not UTF-16.  One additional header row
#   was added (four header rows in total).
# mkqif.py     20190210 2.2   mpw
#   Replace class Financial Institutions by real object instances using
#   constructor parameters
# mkqif.py     20190331 2.3   mpw
#   Split rows based on os.linesep for better portability.
#   Fix bug in credit_debit handling and simplify method interface
#   Modified to work with both Python 2.7 and 3.6
# mkqif.py     20190422 2.4   mpw
#   Moved functions into CSVFormat class
#   CSV rows, QIF text, stats etc are now internal to CSVFormat instance
#   Simplified file processing and error handling
# mkqif.py     20190427 2.5   mpw
#   Enhance configuration file capability to allow  definition of CSVFormats
#   New formats can be added without modifying the source code
# mkqif.py     20190501 2.6   mpw
#   Add -n command argument (no confirmation dialogue)
#   Add -f command argument to override config file default pathname
# mkqif.py     20190602 2.7   mpw
#   Fix mishandling of debit/credit when in same column
# mkqif.py     20190924 2.8   mpw
#   Handle positive debit values
#   Use regexp for credit flag (rename credit_flag to credit_regexp)
#   Handle credit_regexp in payee column
#   Ignore (but count) date format errors
# mkqif.py     20220623 3.0   mpw
#   Add QIF type (CCard/Bank) to CSVFormat definition
#   Change -t option to -i and rename type to fi_name to avoid confusion
#   Specify format of CSV files along with their name on command line
#   Introduce MQException to handle more errors
#   Add -v option
#   Add --no-date-check option
# mkqif.py     20221121 3.1   mpw
#   Add --cutoff-delta option

# for 2.7 print function to handle file= argument
from __future__ import print_function
import codecs
# ConfigParser module name changed between 2.7 and 3.6
try:
    from ConfigParser import ConfigParser
except:
    from configparser import ConfigParser
import csv
import datetime
import getopt
import os
import re
import sys
import time
import traceback
import collections
import locale

# control processing parameters
Params = collections.namedtuple(
    'Parameters','script config_file fi_names output files effective_date '
    'cutoff_date cutoff_delta delete_source institutions output_dir '
    'source_dir qif_suffix check verbose date_check')

# Exception class for mkqif.py
class MQException(Exception):
    '''Exception class for mkqif. '''
    def __init__(self, err):
        self.msg = str(err)
        return

## Function definitions

def str2date(datestr):
    try:
        d = datetime.datetime.strptime(datestr,'%d-%m-%Y')
    except ValueError as e:
        raise MQException(e)
    return datetime.date(d.year,d.month,d.day)

def conv_finame_file_list(finame_files):
    finame_file_list = []
    try:
        for finame_file in finame_files:
            finame, file = finame_file.split(',')
            if finame == ''  or file == '':
                raise MQException("invalid fi_name,CSV_file pair")
            finame_file_list.append((finame, file))
    except ValueError as e:
        raise MQException("invalid fi_name,CSV_file pair: %s" % (e,))
    return finame_file_list

def process_config_file(default_params,pathname):
    """ Read configuraton file date from pathname, alter params as
        specified.  Build CSVFormat instances from sections and key=value
        pairs.  Returns new params."""
    params = default_params
    if os.path.exists(pathname):
        # Disallow interpolation due to use of date formatters in config file
        config = ConfigParser(interpolation=None)
        config.read(pathname)
        try:
            # handle parameters and create CSVFormats from config file
            for inst in config.sections():
                props = {k:v for k,v in config.items(inst)}
                if inst == 'parameters':
                    params = default_params._replace(**props)
                else:
                    props['name'] = inst
                    props['debit_is_negative'] = \
                            config.getboolean(inst, 'debit_is_negative',
                                              fallback = True)
                    CSVFormat(**props)
            fi_names = {'fi_names': CSVFormat.formats.keys(),
                        'institutions': CSVFormat.formats}
            params = params._replace(**fi_names)
        except ValueError as err:
            print("%s: Error in configuration file parameters: %s"%
                  (params.script,err),file=sys.stderr)
            sys.exit(1)
        except TypeError as err:
            print("%s: Cannot create CSVFormat for %s: %s"%
                  (params.script,inst,err),file=sys.stderr)
            sys.exit(1)
    else:
        print("%s: Configuration file '%s' does not exist."%
              (params.script,pathname),file=sys.stderr)
        sys.exit(1)
    return params

def get_matching_files(dir,re_str):
    """Return list of files in dir that match regexp re_str."""
    return [file for file in os.listdir(dir) if re.findall(re_str,file)]

def is_modified_now(pathname,now):
    """Return True if mtime of pathname is the same date as date object now."""
    mtime = time.localtime(os.stat(pathname).st_mtime)
    return mtime.tm_year == now.year and mtime.tm_mon == now.month and \
        mtime.tm_mday == now.day

## Class for CSV formats
#
# define, for each supported institution type:
#  * its name
#  * its type - CCard (default) or Bank
#  * define required set of columns in csv file
#     date_col      - transaction date
#     payee_col     - name of payee
#     debit_col     - amount of transaction
#     credit_col    - credit value or indicator column
#  * credit_regexp: regexp to recognise credit indicator if credit_col
#                   does not contain a value (it is assumed the credit
#                   exists in debit_col)
#  * nheaders:      number of header rows (i.e. initial rows to be ignored)
#  * file_regexp:   regexp string to select csv files from the source_dir
#  * date_format:   date format used in CVS transactions;
#                   format as date.strftime()
#
#  Also, methods for reading the csv file, processing dates, and handling
#  debit/credit amounts, conversion to QIF and display stats.
#
# CSVFormat records instances created in the CSVFormat.formats dictionary

class CSVFormat:
    # Maintain dictionary of instances
    formats = {}

    # CSV processing statistics
    Stats = collections.namedtuple('Stats','valid processed skipped balance '
                                   'empty ncols_mismatch')

    def __init__(self, name='Default', type = 'CCard',
                 date_col=0, payee_col=1, debit_col=2, credit_col=3,
                 ncols=4, nheaders=0, file_regexp=".*\.csv",
                 date_format="%d-%m-%Y", credit_regexp=None,
                 ignore_regexp=None, ignore_col=1, debit_is_negative=True):
        self.name = name
        if type in ('CCard', 'Bank'):
            self.type = type
        else:
            raise MQException('%s: type %s should be CCard or Bank' %
                              (name, type))
        self.date_col = int(date_col)
        self.payee_col = int(payee_col)
        self.debit_col = int(debit_col)
        self.credit_col = int(credit_col)
        self.ncols = int(ncols)
        self.nheaders = int(nheaders)
        self.regexp = file_regexp
        self.date_format = date_format
        self.credit_regexp = credit_regexp
        self.ignore_regexp = ignore_regexp
        self.ignore_col = ignore_col
        self.debit_is_negative = debit_is_negative
        self.csv_rows = []
        self.pathnames = []
        self.qif_text = ""
        self.stats = None
        self.nfiles = 0
        CSVFormat.formats[name] = self # add to class level dictionary
        return

    def reader(self,filename):
        """
        Reading files using latin_1 and encoding with ascii,ignore
        removes weird British pounds sign.
        """
        f = codecs.open(filename,"r","latin_1")
        try:
            ulines = f.read()
        finally:
            f.close()
        # Python 3 - decode to convert bytes returned by codecs.read to str
        # this is a no-op in 2
        lines = ulines.encode('ascii','ignore').decode('ascii')
        return lines.split(os.linesep)[self.nheaders:]

    def str2date(self,date_str,now=None):
        """Return CSVFormat type date string as Python date object."""
        try:
            date = datetime.datetime.strptime(date_str,self.date_format)
            if date.year == 1900:
                year = now.year if date.month <= now.month else now.year-1
            else:
                year = date.year
            return datetime.date(year,date.month,date.day)
        except:
            return None

    def credit_debit(self,row):
        """Handle credits and debits.  debit (amount) and credit are
        extracted from the row array passed in. If credit matches
        credit_regexp, amount is assumed to be a credit value.
        Otherwise, credit is assumed to be a float value and converted
        to a float. A credit is positive, a debit is negative. If this
        convention isn't honoured, set debit_is_negative to False.

        """
        try:
            # remove any embedded spaces in debit string,
            # otherwise locale.atof() errors.
            amount = row[self.debit_col].replace(' ','')
            credit = row[self.credit_col]
            amount = 0 if amount == "" else locale.atof(amount)
            if self.credit_regexp:
                if re.match(self.credit_regexp,credit):
                    return amount if amount >= 0 else -amount
                else:
                    return amount if amount < 0 else -amount
            if self.debit_col == self.credit_col:
                return amount if self.debit_is_negative else -amount
            # valid credit is non-blank and not in the payee column
            # (the payee column is sometimes abused to indicate credit
            # payment)
            if credit != "" and self.credit_col != self.payee_col:
                credit = credit.replace(' ','')
                fcredit = locale.atof(credit)
                if fcredit < 0: fcredit = -fcredit
                if fcredit != 0: return fcredit #!! credit of 0 is not a credit
        except ValueError as e:
            val = ":".join("{:02x}".format(ord(c)) for c in amount)
            raise MQException(f'credit/debit atof() failed: {e} - {val}')
        return -amount if amount > 0 else amount

    def get_csv_rows(self,source_dir, effective_date, date_check, file):
        """Reads csv rows from source_dir/file for financial institution
        type.  If file is None, source_dir is searched for matching
        files for type, where modification date = effective_date,
        unless date_check is False. Returns tuple of CSV rows read and
        source pathnames.

        """
        pathnames = []
        csv_rows = []
        source_dir = source_dir if source_dir[-1] == '/' else source_dir + '/'
        if file:
            pathnames.append(file)
            csv_rows = self.reader(pathnames[0])
        else:
            candidate_files = get_matching_files(source_dir,self.regexp)
            self.nfiles = len(candidate_files)
            if date_check:
                source_files = [file for file in candidate_files
                                if is_modified_now(source_dir + file,
                                                   effective_date)]
            else:
                source_files = candidate_files
            for f in source_files:
                pathnames.append(source_dir+f)
                csv_rows.extend(self.reader(source_dir+f))
        return (csv_rows, pathnames)

    def convert_csv_to_qif(self,cutoff_date,today):
        """Convert csv rows to QIF text.  Record stats. Return QIF."""
        balance = 0.0
        processed = 0
        valid = 0
        empty = 0
        ncols_mismatch = 0
        qif_text = ''
        rows = csv.reader(self.csv_rows)
        for row in rows:
            if self.ignore_regexp and \
               re.match(self.ignore_regexp, row[self.ignore_col]):
                continue
            if len(row) == 0: empty += 1
            elif len(row) != self.ncols:
                ncols_mismatch += 1
            else:
                row_date = self.str2date(row[self.date_col],today)
                if row_date == None:
                    empty += 1
                    continue
                valid += 1
                if row_date < cutoff_date or row_date > today: continue
                payee = re.sub(r' +',' ',row[self.payee_col])
                amount = self.credit_debit(row)
                balance += amount
                processed += 1
                qif_text += "!Type:%s\r\nD%s\r\nT%.02f\r\nP%s\r\n^\r\n"% \
                    (self.type, row_date.strftime("%d-%m-%Y"), amount, payee)
        self.stats = CSVFormat.Stats(valid, processed, valid-processed,
                                     balance, empty, ncols_mismatch)
        return qif_text

    def output_qif(self,output_dir,qif_suffix,dump):
        """Write QIF to terminal, if dump is True.  Else write to file."""
        if  self.qif_text:
            if dump:
                print(self.qif_text)
            else:
                output_dir = output_dir if output_dir[-1] == '/' else \
                    output_dir + '/'
                output_file = output_dir+self.name+qif_suffix
                output = open(output_file,'w')
                output.write(self.qif_text)
                output.close()
        return self.qif_text != ""

    def delete_files(self):
        """Attemp to delete source CSV files."""
        error = None
        for pathname in self.pathnames:
            try:
                os.unlink(pathname)
            except OSError as err:
                if not error: error = err
        return error

    def file_count(self,count):
        return '*' if count > 9 else str(count)

    def display_stats(self):
        if self.stats:
            print("%-10s: Files: %s/%s Rows: %03d/%03d r/w, "\
                  "%03d/%03d c/e. Balance: %8.02f"%
                  (self.name,
                   self.file_count(self.nfiles),
                   self.file_count(len(self.pathnames)),
                   self.stats.valid, self.stats.processed,
                   self.stats.ncols_mismatch, self.stats.empty,
                   self.stats.balance))
        else:
            print("%-10s: No stats have been generated."%(self.name,))
        return

    def perform_conversion(self, source_dir, effective_date, cutoff_date,
                           date_check, file):
        """Convert financial institution type CSV file to QIF."""
        self.csv_rows, self.pathnames = \
            self.get_csv_rows(source_dir, effective_date, date_check, file)
        self.qif_text = self.convert_csv_to_qif(cutoff_date, effective_date)
        return

def process_cmd_args(params,args):
    """
    Parse command line options in args.  Apply configuration file
    settings to default parameters, then apply command arguments.
    Returns new version of params NamedTuple, containing modified
    parameters.
    """
    config_file = params.config_file
    cmd_args = {}
    try:
        opts,files = getopt.getopt(args,'c:d:e:f:i:no:svx',
                                   ('no-date-check', 'cutoff-delta='))
    except getopt.GetoptError as err:
        print("%s: %s"%(params.script,err))
        sys.exit(1)
    try:
        for o,v in opts:
            if o == '-c':
                cmd_args['cutoff_date'] = str2date(v)
            elif o == '-d':
                cmd_args['source_dir'] = v
            elif o == '-e':
                cmd_args['effective_date'] = str2date(v)
            elif o == '-f':
                cmd_args['config_file'] = config_file = v
            elif o == '-i':
                cmd_args['fi_names'] = v.split(',')
            elif o == '-n':
                cmd_args['check'] = False
            elif o == '-o':
                cmd_args['output_dir'] = v
            elif o == '-s':
                cmd_args['output'] = sys.stdout
            elif o == '-x':
                cmd_args['delete_source'] = True
            elif o == '-v':
                cmd_args['verbose'] = True
            elif o == '--no-date-check':
                cmd_args['date_check'] = False
            elif o == '--cutoff-delta':
                try:
                    cmd_args['cutoff_delta'] = datetime.timedelta(int(v))
                except ValueError as e:
                    raise MQException('bad integer value')
    except MQException as e:
        print("%s: option %s: %s" % (params.script, o, e.msg))
        sys.exit(1)

    try:
        params = process_config_file(params,config_file)
        cmd_args['files'] = conv_finame_file_list(files)
        # fi_names from file list overrides -i option
        if len(cmd_args['files']) != 0:
            cmd_args['fi_names'] = [fi_name for fi_name,_ in cmd_args['files']]
    except MQException as e:
        print("%s: %s" % (params.script, e.msg))
        sys.exit(1)
    return params._replace(**cmd_args)

def check(params):
    """
    Set derived params in new params NamedTuple. Asks user to confirm
    parameters before execution. Returns new params.
    """
    # CSVFormats configured?
    if not params.institutions:
        print("%s: no CSV formats have been configured."%(params.script,),
              file=sys.stderr)
        sys.exit(1)
    # set computed parameters
    comp_params = {}
    comp_params['qif_suffix'] = params.effective_date.strftime("%y%m%d.qif")
    if not params.cutoff_date:
        comp_params['cutoff_date'] = params.effective_date - params.cutoff_delta
    params = params._replace(**comp_params)
    # check fi_names
    for name in params.fi_names:
        if name not in params.institutions:
            print("%s: unconfigured institution name: '%s'."\
                  %(params.script,name,),file=sys.stderr)
            sys.exit(1)
    if params.check:
        print("%-30s%s"%("Effective Processing Date:",\
                         params.effective_date.strftime("%d-%m-%Y")))
        print("%-30s%s"%("Historical Cutoff Date:",\
                         params.cutoff_date.strftime("%d-%m-%Y")))
        print("%-30s%s"%("QIF Suffix:",params.qif_suffix))
        print("Hit RETURN to continue (^C to quit)")
        # raw_input is replaced by input in Python 3
        real_raw_input = vars(__builtins__).get('raw_input',input)
        try:
            real_raw_input()
        except KeyboardInterrupt:
            print("OK, quitting ...",file=sys.stderr)
            sys.exit(0)
    return params

def process_fis(params):
    """
    Read csv files and convert to qif files, based on params settings.
    """
    fi_names = params.fi_names
    if len(params.files) == 0:
        nf_dict = zip(fi_names,[None]*len(fi_names))
    else:
        nf_dict = params.files
    source_dir = os.path.expanduser(os.path.expandvars(params.source_dir))
    output_dir = os.path.expanduser(os.path.expandvars(params.output_dir))
    for name, file in nf_dict:
        try:
            inst = params.institutions[name]
            inst.perform_conversion(source_dir, params.effective_date,
                                    params.cutoff_date, params.date_check, file)
            inst.output_qif(output_dir,params.qif_suffix,params.output)
            inst.display_stats()
            if params.delete_source:
                status = inst.delete_files()
                if status:
                    print("%s: %s: source file delete failed: %s\n"%\
                          (params.script,inst.name,status),file=sys.stderr)
        except (OSError, ValueError, IOError) as err:
            print("%s: [%s] Error: %s\n"%(params.script,inst.name,err))
            if params.verbose: traceback.print_tb(sys.exc_info()[2])
            sys.exit(1)
        except MQException as e:
            print("%s: [%s] Error: %s" % (params.script, inst.name, e.msg))
            if params.verbose: traceback.print_tb(sys.exc_info()[2])
            sys.exit(1)
    return

def main(params,args):
    """
    Process financial institutions as specified by configuration
    file and command line args.
    """
    process_fis(check(process_cmd_args(params,args)))
    return

########################################
if __name__ == '__main__':
    # set locale for float conversion
    locale.setlocale(locale.LC_ALL,'')
    params = Params(script = os.path.basename(sys.argv[0]),
                    config_file = 'mkqif.cfg',
                    fi_names = [],
                    files = [],
                    output = None,
                    effective_date = datetime.date.today(),
                    cutoff_delta = datetime.timedelta(7),
                    cutoff_date = None,
                    delete_source = False,
                    institutions = [],
                    output_dir = './',
                    source_dir = './',
                    qif_suffix = None,
                    check = True,
                    verbose = False,
                    date_check = True)
    main(params,sys.argv[1:])

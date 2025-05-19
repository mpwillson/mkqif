# NAME

`mkqif.py` - convert finance CSV files to QIF files.

# SYNOPSIS

```
python mkqif.py [-c cutoff_date] [--cutoff-delta delta]
                [-d source_dir] [-e effective_date]
                [-f config_file] [-i fi_name[,fi_name ...]] [-n]
                [--no-date-check] [-o output_dir] [-s] [-v] [-x]
                [fi_name,csv_file ...]
```

##  Command options:

`-c cutoff_date`
: Transactions earlier than this date will be skipped.  Default is
  seven days prior to effective date.

`--cutoff-delta delta`
: Cutoff date will be computed as delta days before effective
  date. This option will be ignored if `-c` is specified.

`-d source_dir`
: Set directory where CSV files are located.
  Default is ./ (i.e. working directory).

`-e effective_date`
: Sets effective date of conversion.  Default is current date.

`-f config_file`
: Override default configuration file './mkqif.cfg'.

`-i fi_name[,fi_name ...]`
: Sets financial institution (FI) name(s) to convert, as a comma
  separated list.  Default is all defined in
  the configuration file.

`-n`
: No confirmation checkpoint before converting CSV files.

`--no-date-check`
: Do not check modification date of candidate CSV files.

`-o output_dir`
: QIF files are written to output_dir. Default is ./
  (i.e. working directory).

`-s`
: Force output of QIF data to stdout, rather than
  QIF files. Only useful for debugging, probably.

`-v`
: Print stack trace on exceptions.

`-x`
: Delete CSV files, once successfully converted.

The expected date format for command arguments is `dd-mm-yyyy`.

If one or more `fi_name,file` pairs are specified on the command line,
they are processed in preference to searching for files in the
`source_dir`. The `fi_name` component informs `mkqif.py` of the
appropriate conversion for the named CSV `file`. If the `-i` option
has been provided, it will be ignored.

# DESCRIPTION

`mkqif.py` converts financial transaction data from CSV file format to QIF
for subsequent input into Microsoft Money.

Most financial institutions (FI) provide an ability to download
statements and transactions, usually in CSV format. However, each has
its own format and conventions; therefore conversion to QIF requires a
definition of the FI's CSV format.  The conversion is carried out as
defined by `mkqif.py's` configuration file, `mkqif.cfg`. See
CONFIGURATION, below.

CSV files are expected to exist in `source_dir` and to have a
modification date that is the same as the effective date.  This is an
attempt to prevent processing stale financial data. The option
`--no-date-check` eliminates this check. If multiple files match the
criteria, the contents are concatenated into the resulting QIF file.

Output QIF files are written to `output_dir`, with a name of the form
`FInameYYMMDD.qif`, i.e. FI name concatenated with the effective date.

`mkqif.py` prints a cryptic status line for each FI name converted.

# CONFIGURATION
The configuration file, `mkqif.cfg`, is located in the working
directory (unless changed by the `-f` command argument). It is in
Windows .ini format and consists of one or more sections.

The `[parameters]` section is optional and can be used to define
`output_dir` and/or `source_dir`

Other sections define the format of a FI's CSV file. At least one such
format must be defined. The name of the FI is specified as a section
name e.g. `[barclays]`, with formatting specifications provided as
key=value pairs within the section.  Values must not be quoted.

Date formats are converted by the date.strftime() function.  Common
specifiers are:

-  %d - two digit day of month
-  %m - two digit month of year
-  %Y - four digit year
-  %b - abbreviated month (e.g. Jan)

A full list can be found at: https://docs.python.org/3/library/datetime.html

The following example shows all available configuration parameters
for a CSV format for an FI name of barclays:

``` config
; This is a comment
[parameters]
output_dir=~/QIF
source_dir=~/Downloads
[barclays]
; type of account - CCard (default) or Bank
type=Bank
; Number of header lines to skip in CSV
nheaders=2
; Number of columns expected in CSV
ncols=4
; CSV column containing xcn date
date_col=0
; CSV column containing payee name
payee_col=1
; CSV column containing debit amount
debit_col=2
; CSV column containing credit amount (or flag)
credit_col=3
; debit values are positive (i.e. not QIF-like)
debit_is_negative=False
; regexp to select source CSV files
file_regexp=barclays.*csv
; format of xcn date (e.g. 05/Jun/2020)
date_format=%d/%b/%Y
; regexp to indentify credit is in debit column
credit_regexp=PAYMENT.*
; regexp to identify a transaction that should be ignored (e.g. FI commentary)
ignore_regexp=Processing Received Payment
; set column containing ignore value (defaults to 1)
ignore_col=1
```

Configuration file parameter settings are overridden by command line
options.

# NOTES

QIF uses positive values for a credit, negative values for a debit. If
the financial input data doesn't follow this convention or `mkqif.py`
can't disambiguate a credit from a debit, set debit_is_negative to
False.

# EXAMPLES

`./mkqif.py -x`

Convert all CSV files matching FI CSV file criteria, for each FI name
defined in the default configuration file, `./mkqify.cfg`. Delete all
successfully converted CSV files.

`./mkqif.py -c 20-05-2022 -e 25-05-2022 -n barclays,~/downloads/bcl001.csv`

Convert the CSV file named `~/downloads/bcl001.csv`, assuming barclays
format. Ignore transactions earlier than 20-05-2022 and use an
effective date of 25-05-2022. Don't ask for confirmation before
conversion.

`./mkqif.py -f test/test.cfg -s test,test.csv`

Convert test.csv, which is formatted as the test FI. The test FI
format is defined in the `test/test.cfg` configuration file. Output
QIF to stdout.
